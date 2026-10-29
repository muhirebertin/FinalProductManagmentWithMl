# analytics/ml/service.py
"""
Model deployment / inference service.

* Loads the active model versions from the registry (MLModelVersion) and the
  joblib files, and keeps them in memory (thread-safe cache).
* Self-healing: if a model file is missing, or was produced by a different
  scikit-learn version (e.g. after `pip install` on another computer), the
  service retrains automatically from the API data. If there is no training
  data at all, it first generates the synthetic history.
* Exposes high-level business functions used by the dashboard, the web pages
  and the REST API: predict_job, score_task, score_open_tasks, ingest_order.
"""
import datetime as dt
import logging
import math
import threading

import joblib
import sklearn
from django.utils import timezone

from employees.models import Employee, LeaveRequest

from . import features as F

logger = logging.getLogger("analytics")

RISK_THRESHOLDS = (0.35, 0.65)  # < 0.35 Low, < 0.65 Medium, else High
MIN_RECORDS_FOR_TRAINING = 200


class ModelUnavailable(Exception):
    pass


def risk_level(probability):
    if probability is None:
        return ""
    if probability < RISK_THRESHOLDS[0]:
        return "Low"
    if probability < RISK_THRESHOLDS[1]:
        return "Medium"
    return "High"


class PredictorService:
    NAMES = ("delay_classifier", "duration_regressor")

    def __init__(self):
        self._lock = threading.RLock()
        self._cache = {}          # name -> (version_pk, pipeline, label)
        self._bootstrapping = False

    # ------------------------------------------------------------------ loading
    def clear_cache(self):
        with self._lock:
            self._cache.clear()

    def _load(self, name):
        from analytics.models import MLModelVersion
        from .training import model_dir
        active = MLModelVersion.objects.filter(name=name, is_active=True).order_by("-version").first()
        if active is None:
            raise ModelUnavailable(f"No trained '{name}' model yet.")
        cached = self._cache.get(name)
        if cached and cached[0] == active.pk:
            return cached[1], cached[2]
        path = model_dir() / active.file_name
        if not path.exists():
            raise ModelUnavailable(f"Model file {active.file_name} is missing.")
        try:
            bundle = joblib.load(path)
        except Exception as exc:  # corrupted / incompatible pickle
            raise ModelUnavailable(f"Cannot load {active.file_name}: {exc}") from exc
        if bundle.get("sklearn_version") != sklearn.__version__:
            raise ModelUnavailable(
                f"{active.file_name} was trained with scikit-learn {bundle.get('sklearn_version')} "
                f"but {sklearn.__version__} is installed.")
        self._cache[name] = (active.pk, bundle["pipeline"], active.label)
        return bundle["pipeline"], active.label

    def models(self, auto_bootstrap=True):
        """Return {name: (pipeline, label)}; retrain automatically if needed."""
        with self._lock:
            try:
                return {n: self._load(n) for n in self.NAMES}
            except ModelUnavailable as exc:
                if not auto_bootstrap or self._bootstrapping:
                    raise
                logger.warning("AI engine not ready (%s) - bootstrapping automatically.", exc)
                self.bootstrap(reason=str(exc))
                return {n: self._load(n) for n in self.NAMES}

    def bootstrap(self, reason=""):
        from analytics.models import ProductionRecord
        from .synthetic import generate_records
        from .training import train_models
        self._bootstrapping = True
        try:
            if ProductionRecord.objects.count() < MIN_RECORDS_FOR_TRAINING:
                generate_records(clear_existing=False)
            self.clear_cache()
            train_models(trained_by=f"auto-bootstrap: {reason}"[:150])
        finally:
            self._bootstrapping = False

    def status(self):
        """Non-raising readiness check for templates / health endpoint."""
        try:
            loaded = self.models(auto_bootstrap=False)
            return {"ready": True, "versions": {n: v[1] for n, v in loaded.items()}}
        except ModelUnavailable as exc:
            return {"ready": False, "reason": str(exc)}

    # --------------------------------------------------------------- inference
    def predict_features(self, feature_rows):
        """Return [(delay_probability, predicted_days)] for a list of feature dicts."""
        if not feature_rows:
            return [], ""
        loaded = self.models()
        clf, clf_label = loaded["delay_classifier"]
        reg, reg_label = loaded["duration_regressor"]
        classes = list(clf.classes_)
        probs = clf.predict_proba(feature_rows)[:, classes.index(1)]
        days = reg.predict(feature_rows)
        out = [(round(float(p), 4), round(max(0.5, float(d)), 1)) for p, d in zip(probs, days)]
        return out, f"{clf_label}+{reg_label}"


predictor = PredictorService()


# ===========================================================================
# Business-level helpers
# ===========================================================================
def available_artisans(start_date, due_date):
    """Active artisans who are not on approved leave during the job."""
    on_leave = LeaveRequest.objects.filter(
        status="Approved", start_date__lte=due_date, end_date__gte=start_date
    ).values_list("employee_id", flat=True)
    return list(Employee.objects.filter(is_active=True).exclude(pk__in=on_leave)
                .select_related("department").prefetch_related("contracts"))


def _job_dict(profile, quantity, allotted_days, start_date, employee, workload, coverage):
    a = F.artisan_profile(employee)
    return {
        "category": profile["category"],
        "quantity": quantity,
        "unit_price": profile["unit_price"],
        "material_cost_per_unit": profile["material_cost_per_unit"],
        "bom_items": profile["bom_items"],
        "bom_qty_per_unit": profile["bom_qty_per_unit"],
        "allotted_days": allotted_days,
        "start_date": start_date,
        "artisan_contract": a["artisan_contract"],
        "artisan_department": a["artisan_department"],
        "artisan_workload": workload,
        "stock_coverage": coverage,
    }


def _recommendations(result, profile):
    recs = []
    for s in result["shortages"]:
        recs.append(f"Restock {s['material']}: {s['missing']} {s['unit']} missing "
                    f"(need {s['required']}, have {s['in_stock']}). The task cannot be created until then.")
    chosen = result.get("artisan")
    best = result.get("recommended_artisan")
    if chosen and best and best["id"] != chosen["id"] and \
            best["delay_probability"] + 0.10 < result["delay_probability"]:
        recs.append(f"Assign to {best['name']} instead: delay risk drops from "
                    f"{round(result['delay_probability'] * 100)}% to {round(best['delay_probability'] * 100)}%.")
    if chosen and chosen.get("workload", 0) >= 3:
        recs.append(f"{chosen['name']} already has {chosen['workload']} active tasks; consider rebalancing.")
    if result["predicted_days"] > result["allotted_days"]:
        safe_days = math.ceil(result["predicted_days"] * 1.1)
        recs.append(f"Expected duration ({result['predicted_days']} days) exceeds the time allowed "
                    f"({result['allotted_days']} days). Allow about {safe_days} days or split the batch.")
    if not recs:
        recs.append("On track: the current plan is realistic. Standard scheduling is sufficient.")
    return recs


def predict_job(product, quantity, due_date, employee=None, start_date=None, rank_artisans=True,
                stock_coverage=None, exclude_task_id=None):
    """
    Predict the outcome of producing `quantity` x `product` by `due_date`.
    If `employee` is None the best available artisan is chosen automatically.
    """
    start_date = F.to_date(start_date or timezone.localdate())
    due_date = F.to_date(due_date)
    quantity = max(1, int(quantity))
    allotted = max(1, (due_date - start_date).days)
    profile = F.product_profile(product)
    if stock_coverage is None:
        coverage, shortages = F.stock_check(product, quantity)
    else:
        coverage, shortages = stock_coverage, []
    hist = F.artisan_history_from_db()

    candidates = available_artisans(start_date, due_date) if rank_artisans else []
    if employee is not None and all(c.pk != employee.pk for c in candidates):
        candidates.append(employee)
    if not candidates:
        candidates = [None]

    rows, meta = [], []
    for emp in candidates:
        workload = F.artisan_workload(emp, exclude_task_id)
        job = _job_dict(profile, quantity, allotted, start_date, emp, workload, coverage)
        rows.append(F.build_features(job, hist.get(emp.pk) if emp else None))
        meta.append((emp, workload))
    scores, version = predictor.predict_features(rows)

    ranking = []
    for (emp, workload), (prob, days), feats in zip(meta, scores, rows):
        ranking.append({
            "id": emp.pk if emp else None,
            "name": f"{emp.first_name} {emp.last_name}" if emp else "Unassigned",
            "department": emp.department.name if emp else "",
            "contract": feats["artisan_contract"],
            "workload": workload,
            "delay_probability": prob,
            "risk_level": risk_level(prob),
            "predicted_days": days,
            "dept_match": bool(feats["dept_match"]),
            "_features": feats,
        })
    ranking.sort(key=lambda r: (r["delay_probability"], r["predicted_days"]))
    best = ranking[0]
    chosen = next((r for r in ranking if employee is not None and r["id"] == employee.pk), best)

    result = {
        "product": {"code": product.code, "name": product.name, "category": product.category},
        "quantity": quantity,
        "start_date": start_date.isoformat(),
        "due_date": due_date.isoformat(),
        "allotted_days": allotted,
        "standard_days": chosen["_features"]["standard_days"],
        "delay_probability": chosen["delay_probability"],
        "risk_level": chosen["risk_level"],
        "predicted_days": chosen["predicted_days"],
        "predicted_completion": (start_date + dt.timedelta(days=math.ceil(chosen["predicted_days"]))).isoformat(),
        "expected_delay_days": round(max(0.0, chosen["predicted_days"] - allotted), 1),
        "artisan": None if chosen["id"] is None else {k: v for k, v in chosen.items() if not k.startswith("_")},
        "recommended_artisan": None if best["id"] is None else {k: v for k, v in best.items() if not k.startswith("_")},
        "artisan_ranking": [{k: v for k, v in r.items() if not k.startswith("_")} for r in ranking],
        "stock_ok": not shortages,
        "blocked": bool(shortages),  # the existing stock rule refuses the task until restocked
        "stock_coverage": coverage,
        "shortages": shortages,
        "features": chosen["_features"],
        "model_version": version,
    }
    result["recommendations"] = _recommendations(result, profile)
    return result


def score_task(task):
    """AI assessment of an existing ProductionTask."""
    base = {"task_id": task.pk, "status": task.status, "progress": task.progress_percentage}
    if task.status == "Completed":
        return {**base, "state": "completed", "risk_level": "", "label": "Completed"}
    if task.product is None:
        return {**base, "state": "unscorable", "risk_level": "", "label": "No product"}
    if task.is_overdue:
        return {**base, "state": "overdue", "risk_level": "High", "delay_probability": 1.0,
                "label": "Overdue", "recommendations": [
                    "This task is past its due date. Re-plan the due date or add capacity."]}
    start = timezone.localtime(task.created_at).date() if task.created_at else timezone.localdate()
    due = max(task.due_date, start + dt.timedelta(days=1))
    # Materials were already reserved when the task was created, so stock is not a risk factor.
    result = predict_job(task.product, task.target_quantity, due, employee=task.assigned_to,
                         start_date=start, rank_artisans=task.assigned_to is None,
                         stock_coverage=F.STOCK_COVERAGE_CAP, exclude_task_id=task.pk)
    result.update(base)
    result["state"] = "scored"
    result["label"] = result["risk_level"]
    # Progress-based projection for tasks already under way
    elapsed = (timezone.localdate() - start).days
    if task.status == "In Progress" and task.produced_quantity > 0 and elapsed > 0:
        rate = task.produced_quantity / elapsed
        remaining = task.target_quantity - task.produced_quantity
        finish = timezone.localdate() + dt.timedelta(days=math.ceil(remaining / rate))
        result["progress_projection"] = finish.isoformat()
        result["projection_late"] = finish > task.due_date
    return result


def score_open_tasks(limit=None):
    from production.models import ProductionTask
    qs = (ProductionTask.objects.exclude(status="Completed")
          .select_related("product", "assigned_to__department").order_by("due_date"))
    if limit:
        qs = qs[:limit]
    scored = []
    for task in qs:
        try:
            scored.append((task, score_task(task)))
        except ModelUnavailable:
            raise
        except Exception as exc:  # never let one bad row break the dashboard
            logger.exception("Could not score task %s: %s", task.pk, exc)
            scored.append((task, {"state": "error", "label": "n/a", "risk_level": ""}))
    order = {"High": 0, "Medium": 1, "Low": 2, "": 3}
    scored.sort(key=lambda t: (order.get(t[1].get("risk_level", ""), 3), -(t[1].get("delay_probability") or 0)))
    return scored


# ---------------------------------------------------------------------------
# Incoming data ingestion
# ---------------------------------------------------------------------------
class OrderValidationError(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def _next_reference():
    from analytics.models import IncomingOrder
    stamp = timezone.localtime().strftime("%y%m%d")
    count = IncomingOrder.objects.filter(reference__startswith=f"ORD-{stamp}").count() + 1
    ref = f"ORD-{stamp}-{count:04d}"
    while IncomingOrder.objects.filter(reference=ref).exists():
        count += 1
        ref = f"ORD-{stamp}-{count:04d}"
    return ref


def validate_order_payload(payload):
    from inventory.models import Product
    errors, clean = {}, {}
    code = str(payload.get("product_code") or "").strip()
    product = Product.objects.filter(code__iexact=code).first() if code else None
    if not code:
        errors["product_code"] = "This field is required."
    elif product is None:
        errors["product_code"] = f"Unknown product code '{code}'."
    try:
        quantity = int(payload.get("quantity"))
        if quantity < 1 or quantity > 10000:
            raise ValueError
    except (TypeError, ValueError):
        errors["quantity"] = "Must be an integer between 1 and 10000."
        quantity = None
    due = payload.get("due_date")
    try:
        due = F.to_date(due) if due else None
        if due is None:
            errors["due_date"] = "This field is required (YYYY-MM-DD)."
        elif due <= timezone.localdate():
            errors["due_date"] = "Due date must be in the future."
    except ValueError:
        errors["due_date"] = "Invalid date. Use YYYY-MM-DD."
    employee = None
    if payload.get("artisan_id") not in (None, ""):
        employee = Employee.objects.filter(pk=payload.get("artisan_id"), is_active=True).first()
        if employee is None:
            errors["artisan_id"] = "Unknown or inactive artisan."
    channel = payload.get("channel") or "Storefront"
    from analytics.models import IncomingOrder
    if channel not in dict(IncomingOrder.CHANNEL_CHOICES):
        errors["channel"] = f"Must be one of: {', '.join(dict(IncomingOrder.CHANNEL_CHOICES))}."
    if errors:
        raise OrderValidationError(errors)
    clean.update(product=product, quantity=quantity, due_date=due, employee=employee, channel=channel,
                 customer=str(payload.get("customer") or "")[:120])
    return clean


def ingest_order(payload, user=None, source="api"):
    """Validate, store and score a new incoming order. Returns the IncomingOrder."""
    from analytics.models import IncomingOrder, PredictionLog
    data = validate_order_payload(payload)
    result = predict_job(data["product"], data["quantity"], data["due_date"], employee=data["employee"])
    rec = result["recommended_artisan"]
    order = IncomingOrder.objects.create(
        reference=_next_reference(),
        customer=data["customer"],
        channel=data["channel"],
        product=data["product"],
        product_code=data["product"].code,
        quantity=data["quantity"],
        due_date=data["due_date"],
        requested_artisan=data["employee"],
        source=source,
        delay_probability=result["delay_probability"],
        risk_level=result["risk_level"],
        predicted_days=result["predicted_days"],
        predicted_completion=F.to_date(result["predicted_completion"]),
        recommended_artisan_id=rec["id"] if rec else None,
        stock_ok=result["stock_ok"],
        prediction=result,
        model_version=result["model_version"],
    )
    PredictionLog.objects.create(kind="order", object_ref=order.reference, inputs=payload_safe(payload),
                                 outputs=_slim(result), model_version=result["model_version"],
                                 user=user if (user and user.is_authenticated) else None)
    return order


def payload_safe(payload):
    return {k: (v if isinstance(v, (str, int, float, bool, type(None))) else str(v)) for k, v in dict(payload).items()}


def _slim(result):
    keys = ("delay_probability", "risk_level", "predicted_days", "predicted_completion",
            "expected_delay_days", "stock_ok", "recommendations")
    out = {k: result.get(k) for k in keys}
    out["artisan"] = (result.get("artisan") or {}).get("name")
    out["recommended_artisan"] = (result.get("recommended_artisan") or {}).get("name")
    return out

