# analytics/ml/features.py
"""
Feature engineering - the single source of truth shared by
  * the synthetic data generator,
  * the training pipeline (features built from API JSON records), and
  * live inference (features built from Django model instances).

Using one module for all three guarantees that the model sees the same
features in production as it saw during training.
"""
import bisect
import datetime as dt
import math
from collections import defaultdict
from decimal import Decimal

# Engineering standard: labour hours needed for ONE unit of each category.
CATEGORY_HOURS = {
    "Bags": 3.0,
    "Shoes": 4.0,
    "Belts": 1.2,
    "Folders": 1.0,
    "Accessories": 0.6,
}
DEFAULT_CATEGORY_HOURS = 1.5
HOURS_PER_DAY = 8.0

# The department whose skills naturally match each product category.
CATEGORY_DEPARTMENT_KEYWORD = {
    "Bags": "stitching",
    "Folders": "stitching",
    "Belts": "cutting",
    "Shoes": "finishing",
    "Accessories": "packaging",
}

# Typical batch-size ranges per category (used by the generators).
CATEGORY_QTY_RANGE = {
    "Bags": (2, 25),
    "Shoes": (4, 40),
    "Belts": (5, 60),
    "Folders": (5, 50),
    "Accessories": (10, 80),
}

STOCK_COVERAGE_CAP = 5.0
DEFAULT_HIST_ONTIME = 0.70
DEFAULT_HIST_EFFICIENCY = 1.0


def _f(value, default=0.0):
    """Convert Decimal / None / str to float safely."""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------
def standard_days(category, quantity, bom_items, bom_qty_per_unit):
    """Engineering standard duration of a batch, in working days."""
    base = CATEGORY_HOURS.get(category, DEFAULT_CATEGORY_HOURS)
    hours_per_unit = base * (1 + 0.06 * bom_items) * (1 + 0.015 * min(bom_qty_per_unit, 20))
    return round(max(0.5, quantity * hours_per_unit / HOURS_PER_DAY), 2)


def department_matches(category, department_name):
    keyword = CATEGORY_DEPARTMENT_KEYWORD.get(category)
    if not keyword or not department_name:
        return False
    return keyword in department_name.lower()


def product_profile(product):
    """Static facts about a product derived from its Bill of Materials."""
    boms = list(product.bom_items.select_related("material").all())
    bom_qty = sum(_f(b.quantity_per_unit) for b in boms)
    material_cost = sum(_f(b.quantity_per_unit) * _f(b.material.unit_cost) for b in boms)
    return {
        "product_code": product.code,
        "product_name": product.name,
        "category": product.category,
        "unit_price": _f(product.unit_price),
        "material_cost_per_unit": round(material_cost, 2),
        "bom_items": len(boms),
        "bom_qty_per_unit": round(bom_qty, 4),
        "boms": boms,
    }


def stock_check(product, quantity):
    """
    Compare the BOM requirement of a batch with the warehouse stock.
    Returns (coverage_ratio, shortages) where coverage is min(stock/need),
    capped at STOCK_COVERAGE_CAP.
    """
    coverage = STOCK_COVERAGE_CAP
    shortages = []
    for bom in product.bom_items.select_related("material").all():
        need = _f(bom.quantity_per_unit) * quantity
        have = _f(bom.material.quantity_in_stock)
        if need <= 0:
            continue
        ratio = have / need
        coverage = min(coverage, ratio)
        if have < need:
            shortages.append({
                "material_code": bom.material.code,
                "material": bom.material.name,
                "unit": bom.material.unit,
                "required": round(need, 2),
                "in_stock": round(have, 2),
                "missing": round(need - have, 2),
            })
    return round(min(coverage, STOCK_COVERAGE_CAP), 3), shortages


def artisan_profile(employee):
    if employee is None:
        return {"artisan_contract": "None", "artisan_department": "", "artisan_name": ""}
    contract = employee.active_contract
    return {
        "artisan_contract": contract if contract != "No Contract" else "None",
        "artisan_department": employee.department.name if employee.department_id else "",
        "artisan_name": f"{employee.first_name} {employee.last_name}",
    }


def artisan_workload(employee, exclude_task_id=None):
    if employee is None:
        return 0
    qs = employee.tasks.filter(status__in=["Pending", "In Progress"])
    if exclude_task_id:
        qs = qs.exclude(pk=exclude_task_id)
    return qs.count()


# ---------------------------------------------------------------------------
# Feature vector
# ---------------------------------------------------------------------------
FEATURE_DESCRIPTIONS = {
    "category": "Product category (one-hot encoded)",
    "quantity": "Batch size (units)",
    "unit_price": "Selling price per unit (RWF)",
    "material_cost_per_unit": "BOM material cost per unit (RWF)",
    "bom_items": "Number of distinct materials in the BOM",
    "bom_qty_per_unit": "Total material quantity per unit",
    "standard_days": "Engineering standard duration (days)",
    "allotted_days": "Days allowed by the manager",
    "slack_ratio": "Allotted days / standard days",
    "required_rate": "Units per day required to meet the due date",
    "artisan_contract": "Contract type of the artisan (one-hot)",
    "dept_match": "Artisan's department matches the product category",
    "artisan_workload": "Other active tasks of the artisan",
    "artisan_hist_ontime": "Artisan's historical on-time rate",
    "artisan_hist_efficiency": "Artisan's historical speed (standard / actual)",
    "stock_coverage": "Warehouse coverage of the BOM requirement",
    "month": "Month the batch starts",
    "peak_season": "Starts in Nov/Dec peak season",
}


def build_features(job, hist=None):
    """
    Build the model input dictionary from a *job* dict containing:
    category, quantity, unit_price, material_cost_per_unit, bom_items,
    bom_qty_per_unit, allotted_days, start_date, artisan_contract,
    artisan_department, artisan_workload, stock_coverage
    and optionally standard_days / dept_match.
    `hist` = (on_time_rate, efficiency) for the artisan.
    """
    category = job.get("category") or "Unknown"
    quantity = max(1, int(_f(job.get("quantity"), 1)))
    bom_items = int(_f(job.get("bom_items")))
    bom_qty = _f(job.get("bom_qty_per_unit"))
    std = _f(job.get("standard_days")) or standard_days(category, quantity, bom_items, bom_qty)
    allotted = max(1, int(_f(job.get("allotted_days"), 1)))
    start = to_date(job.get("start_date") or dt.date.today())
    if "dept_match" in job and job["dept_match"] is not None:
        dept_match = bool(job["dept_match"])
    else:
        dept_match = department_matches(category, job.get("artisan_department", ""))
    ontime, efficiency = hist if hist else (DEFAULT_HIST_ONTIME, DEFAULT_HIST_EFFICIENCY)

    return {
        "category": str(category),
        "quantity": float(quantity),
        "unit_price": _f(job.get("unit_price")),
        "material_cost_per_unit": _f(job.get("material_cost_per_unit")),
        "bom_items": float(bom_items),
        "bom_qty_per_unit": bom_qty,
        "standard_days": std,
        "allotted_days": float(allotted),
        "slack_ratio": round(allotted / std, 4) if std else 1.0,
        "required_rate": round(quantity / allotted, 4),
        "artisan_contract": str(job.get("artisan_contract") or "None"),
        "dept_match": 1.0 if dept_match else 0.0,
        "artisan_workload": _f(job.get("artisan_workload")),
        "artisan_hist_ontime": round(_f(ontime, DEFAULT_HIST_ONTIME), 4),
        "artisan_hist_efficiency": round(_f(efficiency, DEFAULT_HIST_EFFICIENCY), 4),
        "stock_coverage": min(_f(job.get("stock_coverage"), STOCK_COVERAGE_CAP), STOCK_COVERAGE_CAP),
        "month": float(start.month),
        "peak_season": 1.0 if start.month in (11, 12) else 0.0,
    }


# ---------------------------------------------------------------------------
# Artisan history features
# ---------------------------------------------------------------------------
def _efficiency(rec):
    actual = _f(rec.get("actual_days"))
    std = _f(rec.get("standard_days"))
    return std / actual if actual > 0 else DEFAULT_HIST_EFFICIENCY


def build_training_rows(records):
    """
    Turn a list of record dicts (as returned by the API) into
    (X_dicts, y_delayed, y_days, start_dates).

    Artisan history features are computed *only from batches that finished
    before the current batch started*, so there is no target leakage.
    """
    records = sorted(records, key=lambda r: (str(r["start_date"]), r.get("id", 0)))
    finished = defaultdict(list)          # artisan_id -> list sorted by end_date
    for r in records:
        aid = r.get("artisan_id")
        if aid is None:
            continue
        finished[aid].append((to_date(r["end_date"]), 0 if r["delayed"] else 1, _efficiency(r)))
    prefix = {}
    for aid, rows in finished.items():
        rows.sort(key=lambda t: t[0])
        ends, ok_cum, eff_cum = [], [0], [0.0]
        for end, ok, eff in rows:
            ends.append(end)
            ok_cum.append(ok_cum[-1] + ok)
            eff_cum.append(eff_cum[-1] + eff)
        prefix[aid] = (ends, ok_cum, eff_cum)

    X, y_delay, y_days, dates = [], [], [], []
    for r in records:
        aid = r.get("artisan_id")
        hist = None
        if aid in prefix:
            ends, ok_cum, eff_cum = prefix[aid]
            k = bisect.bisect_left(ends, to_date(r["start_date"]))
            if k >= 3:  # need a minimum history to be meaningful
                hist = (ok_cum[k] / k, eff_cum[k] / k)
        X.append(build_features(r, hist))
        y_delay.append(1 if r["delayed"] else 0)
        y_days.append(_f(r["actual_days"]))
        dates.append(to_date(r["start_date"]))
    return X, y_delay, y_days, dates


def artisan_history_from_db():
    """{artisan_id: (on_time_rate, efficiency)} using all recorded history."""
    from django.core.cache import cache
    cached = cache.get("analytics:artisan_hist")
    if cached is not None:
        return cached
    from analytics.models import ProductionRecord
    agg = defaultdict(lambda: [0, 0, 0.0])
    for aid, delayed, actual, std in ProductionRecord.objects.exclude(artisan__isnull=True).values_list(
            "artisan_id", "delayed", "actual_days", "standard_days"):
        a = agg[aid]
        a[0] += 1
        a[1] += 0 if delayed else 1
        a[2] += (std / actual) if actual else 1.0
    result = {aid: (a[1] / a[0], a[2] / a[0]) for aid, a in agg.items() if a[0] >= 3}
    cache.set("analytics:artisan_hist", result, 300)
    return result


def invalidate_history_cache():
    from django.core.cache import cache
    cache.delete("analytics:artisan_hist")


def safe_ceil(x):
    return int(math.ceil(max(0.0, _f(x))))
