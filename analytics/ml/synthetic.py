# analytics/ml/synthetic.py
"""
Synthetic historical data generator.

The live database only holds a handful of production tasks, which is far too
little to train a machine-learning model. This module generates a realistic
history of finished batches *based on the real catalogue*: real products,
their real Bills of Materials, real artisans, departments and contracts.

The outcome of every batch is produced by a transparent causal process:

    actual_days = standard_days
                  x artisan skill            (hidden, per artisan)
                  x contract factor          (Intern slower, Permanent faster)
                  x (1 + 0.08 x workload)    (concurrent tasks slow people down)
                  x 1.18 if the artisan works outside their speciality
                  x 1.15 in the Nov/Dec peak season
                  x log-normal noise         (sigma = 0.18)
                  + restock wait when stock was insufficient:
                    2 + 10 x (1 - coverage) + U(0, 3) days

    delayed = actual_days > allotted_days

The generator is deterministic for a given seed so results are reproducible.
"""
import datetime as dt
import math
import random

from django.db import transaction

from employees.models import Employee
from inventory.models import Product

from . import features as F

CONTRACT_FACTOR = {"Permanent": 0.95, "Temporary": 1.05, "Intern": 1.20, "None": 1.10}


def _artisan_skill(employee_id, seed):
    rnd = random.Random(f"skill-{seed}-{employee_id}")
    return round(rnd.uniform(0.75, 1.20), 3)


def generate_records(n=2000, days_back=540, seed=42, clear_existing=True, end_date=None):
    """
    Generate `n` synthetic ProductionRecord rows spread over the last
    `days_back` days. Returns the number of records created.
    """
    from analytics.models import ProductionRecord

    rnd = random.Random(seed)
    products = [p for p in Product.objects.prefetch_related("bom_items__material").all()]
    if not products:
        raise ValueError("No products found. Create at least one product with a BOM first.")
    employees = list(Employee.objects.select_related("department").all())

    profiles = {p.pk: F.product_profile(p) for p in products}
    artisans = []
    for e in employees:
        prof = F.artisan_profile(e)
        artisans.append((e, prof, _artisan_skill(e.pk, seed)))

    end_date = end_date or dt.date.today()
    start_window = end_date - dt.timedelta(days=days_back)
    rows = []
    for _ in range(n):
        product = rnd.choice(products)
        prof = profiles[product.pk]
        category = prof["category"]
        lo, hi = F.CATEGORY_QTY_RANGE.get(category, (2, 30))
        quantity = rnd.randint(lo, hi)

        # Choose an artisan, preferring someone from the matching department.
        if artisans:
            matching = [a for a in artisans if F.department_matches(category, a[1]["artisan_department"])]
            pool = matching if (matching and rnd.random() < 0.55) else artisans
            employee, a_prof, skill = rnd.choice(pool)
        else:
            employee, a_prof, skill = None, F.artisan_profile(None), 1.1

        start = start_window + dt.timedelta(days=rnd.randint(0, days_back - 1))
        std = F.standard_days(category, quantity, prof["bom_items"], prof["bom_qty_per_unit"])
        allotted = max(1, int(math.ceil(std * rnd.uniform(0.90, 1.75))))

        peak = start.month in (11, 12)
        workload = min(8, int(rnd.expovariate(1 / (2.2 if peak else 1.4))))
        coverage = round(min(F.STOCK_COVERAGE_CAP, rnd.lognormvariate(1.0, 0.6)), 3)
        if rnd.random() < 0.12:
            coverage = round(rnd.uniform(0.05, 0.98), 3)  # material shortage at start
        dept_match = F.department_matches(category, a_prof["artisan_department"])

        actual = std * skill * CONTRACT_FACTOR.get(a_prof["artisan_contract"], 1.1)
        actual *= (1 + 0.08 * workload)
        actual *= 1.0 if dept_match else 1.18
        actual *= 1.15 if peak else 1.0
        actual *= rnd.lognormvariate(0, 0.18)
        if coverage < 1.0:  # waiting for the restock: the bigger the gap, the longer the wait
            actual += 2 + 10 * (1 - coverage) + rnd.uniform(0, 3)
        actual = round(max(0.5, actual), 1)

        defect_p = min(0.25, 0.015 * skill * (1 + 0.05 * prof["bom_items"]) * (1.4 if not dept_match else 1.0))
        defects = sum(1 for _ in range(quantity) if rnd.random() < defect_p)

        rows.append(ProductionRecord(
            product=product,
            artisan=employee,
            product_code=prof["product_code"],
            product_name=prof["product_name"],
            category=category,
            quantity=quantity,
            unit_price=prof["unit_price"],
            material_cost_per_unit=prof["material_cost_per_unit"],
            bom_items=prof["bom_items"],
            bom_qty_per_unit=prof["bom_qty_per_unit"],
            standard_days=std,
            allotted_days=allotted,
            artisan_name=a_prof["artisan_name"],
            artisan_contract=a_prof["artisan_contract"],
            artisan_department=a_prof["artisan_department"],
            dept_match=dept_match,
            artisan_workload=workload,
            stock_coverage=coverage,
            start_date=start,
            due_date=start + dt.timedelta(days=allotted),
            end_date=start + dt.timedelta(days=int(math.ceil(actual))),
            actual_days=actual,
            delayed=actual > allotted,
            defective_units=defects,
            source="synthetic",
        ))

    with transaction.atomic():
        if clear_existing:
            ProductionRecord.objects.filter(source="synthetic").delete()
        ProductionRecord.objects.bulk_create(rows, batch_size=500)
    F.invalidate_history_cache()
    return len(rows)


# ---------------------------------------------------------------------------
# Incoming-order simulator payloads
# ---------------------------------------------------------------------------
CUSTOMERS = [
    "Kigali Heights Boutique", "Muhanga City Council", "Rubavu Lakeside Hotel",
    "Inzozi Fashion House", "Bank of Kigali HQ", "Akagera Safari Lodge",
    "Huye University Bookshop", "Nyamirambo Shoe Gallery", "Musanze Outfitters",
    "RwandAir Crew Supplies", "Kimironko Market Stall 14", "Export: Nairobi Leather Co.",
]
CHANNELS = ["Storefront", "Corporate", "Online", "Export"]


def random_order_payload(rnd=None, allow_artisan=True):
    """A realistic JSON payload for POST /api/v1/orders/."""
    rnd = rnd or random.Random()
    products = list(Product.objects.prefetch_related("bom_items").all())
    if not products:
        raise ValueError("No products available to simulate orders.")
    product = rnd.choice(products)
    prof = F.product_profile(product)
    lo, hi = F.CATEGORY_QTY_RANGE.get(product.category, (2, 30))
    quantity = rnd.randint(lo, max(lo, int(hi * 0.6)))
    std = F.standard_days(product.category, quantity, prof["bom_items"], prof["bom_qty_per_unit"])
    allotted = max(2, int(math.ceil(std * rnd.uniform(0.85, 1.8))))
    payload = {
        "product_code": product.code,
        "quantity": quantity,
        "due_date": (dt.date.today() + dt.timedelta(days=allotted)).isoformat(),
        "customer": rnd.choice(CUSTOMERS),
        "channel": rnd.choice(CHANNELS),
    }
    if allow_artisan and rnd.random() < 0.4:
        active = list(Employee.objects.filter(is_active=True).values_list("pk", flat=True))
        if active:
            payload["artisan_id"] = rnd.choice(active)
    return payload
