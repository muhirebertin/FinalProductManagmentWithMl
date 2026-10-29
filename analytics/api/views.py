# analytics/api/views.py
"""
REST API v1 for the Le Mieux Production Management System.
See the API Center page (/analytics/api/) for full documentation.
"""
import datetime as dt
import math

from django.db.models import F as DbF
from django.urls import reverse
from django.utils import timezone

from employees.models import Employee
from inventory.models import Product, RawMaterial
from production.models import ProductionTask

from ..ml import features as Feat
from ..ml import insights, service
from ..ml.external import fetch_usd_rwf
from ..ml.service import ModelUnavailable, OrderValidationError, predictor
from ..ml.training import TrainingError, train_models
from ..models import IncomingOrder, MLModelVersion, PredictionLog, ProductionRecord
from . import serializers as S
from .auth import api_endpoint, error, ok, read_json

API_VERSION = "1.0"


def _int(value, default, lo=1, hi=None):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    v = max(lo, v)
    return min(v, hi) if hi else v


def _paginate(request, queryset, default_size=100, max_size=5000):
    size = _int(request.GET.get("page_size"), default_size, 1, max_size)
    total = queryset.count()
    pages = max(1, math.ceil(total / size))
    page = _int(request.GET.get("page"), 1, 1, pages)
    items = queryset[(page - 1) * size: page * size]
    return items, {"page": page, "pages": pages, "page_size": size, "total": total}


# ---------------------------------------------------------------- discovery
@api_endpoint(public=True)
def api_index(request):
    def u(name, *args):
        return reverse(f"api:{name}", args=args)
    return ok({
        "name": "Le Mieux Production Management API", "version": API_VERSION,
        "authentication": "Header 'X-API-Key: <key>' or an authenticated browser session.",
        "endpoints": {
            "health": {"GET": u("health")},
            "products": {"GET": u("products")},
            "materials": {"GET": u("materials")},
            "employees": {"GET": u("employees")},
            "tasks": {"GET": u("tasks")},
            "task_prediction": {"GET": u("task_prediction", 1).replace("/1/", "/<id>/")},
            "records": {"GET": u("records"), "POST": u("records")},
            "orders": {"GET": u("orders"), "POST": u("orders")},
            "order_detail": {"GET": u("order_detail", 1).replace("/1/", "/<id>/")},
            "predict": {"POST": u("predict")},
            "model": {"GET": u("model")},
            "model_retrain": {"POST": u("model_retrain")},
            "dashboard_summary": {"GET": u("dashboard_summary")},
            "material_forecast": {"GET": u("material_forecast")},
            "fx_rate": {"GET": u("fx_rate")},
        },
    })


@api_endpoint(public=True)
def health(request):
    status = predictor.status()
    return ok({"service": "up", "database": "up", "ai_engine": "ready" if status["ready"] else "not ready",
               "models": status.get("versions", {}), "detail": status.get("reason", ""),
               "time": timezone.now().isoformat()})


# ---------------------------------------------------------------- read-only resources
@api_endpoint()
def products(request):
    qs = Product.objects.prefetch_related("bom_items__material").order_by("code")
    if request.GET.get("category"):
        qs = qs.filter(category__iexact=request.GET["category"])
    return ok([S.product_to_dict(p) for p in qs], count=qs.count())


@api_endpoint()
def materials(request):
    qs = RawMaterial.objects.order_by("code")
    if request.GET.get("low_stock") in ("1", "true", "yes"):
        qs = qs.filter(quantity_in_stock__lte=DbF("reorder_level"))
    return ok([S.material_to_dict(m) for m in qs], count=qs.count(),
              inventory_value_rwf=insights.inventory_value())


@api_endpoint()
def employees(request):
    qs = Employee.objects.select_related("department").prefetch_related("contracts").order_by("last_name")
    if request.GET.get("active") in ("1", "true", "yes"):
        qs = qs.filter(is_active=True)
    return ok([S.employee_to_dict(e) for e in qs], count=qs.count())


@api_endpoint()
def tasks(request):
    qs = ProductionTask.objects.select_related("product", "assigned_to").order_by("-created_at")
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status__iexact=status)
    return ok([S.task_to_dict(t) for t in qs], count=qs.count())


@api_endpoint()
def task_prediction(request, pk):
    task = ProductionTask.objects.select_related("product", "assigned_to").filter(pk=pk).first()
    if task is None:
        return error("not_found", f"Task {pk} not found.", 404)
    try:
        result = service.score_task(task)
    except ModelUnavailable as exc:
        return error("model_unavailable", str(exc), 503)
    PredictionLog.objects.create(kind="task", object_ref=f"TSK-{pk}", inputs={"task_id": pk},
                                 outputs=service._slim(result) if result.get("state") == "scored" else result,
                                 model_version=result.get("model_version", ""), user=request.api_user)
    return ok({"task": S.task_to_dict(task), "assessment": result})


# ---------------------------------------------------------------- historical records (training data)
REQUIRED_RECORD_FIELDS = ("product_code", "quantity", "start_date", "due_date", "end_date")


@api_endpoint(methods=("GET", "POST"))
def records(request):
    if request.method == "GET":
        qs = ProductionRecord.objects.all().order_by("start_date", "id")
        if request.GET.get("source"):
            qs = qs.filter(source=request.GET["source"])
        if request.GET.get("since"):
            try:
                qs = qs.filter(start_date__gte=dt.date.fromisoformat(request.GET["since"]))
            except ValueError:
                return error("invalid_parameter", "'since' must be YYYY-MM-DD.")
        items, meta = _paginate(request, qs, default_size=500)
        return ok([S.record_to_dict(r) for r in items], **meta)

    # POST: an external system (MES terminal, partner workshop) pushes a finished batch
    try:
        data = read_json(request)
    except ValueError as exc:
        return error("invalid_json", f"Invalid JSON body: {exc}")
    missing = [f for f in REQUIRED_RECORD_FIELDS if not data.get(f)]
    if missing:
        return error("validation_error", "Missing required fields.", details={f: "required" for f in missing})
    product = Product.objects.filter(code__iexact=str(data["product_code"])).prefetch_related(
        "bom_items__material").first()
    if product is None:
        return error("validation_error", "Unknown product.", details={"product_code": "not found"})
    try:
        quantity = int(data["quantity"])
        start, due, end = (Feat.to_date(data[k]) for k in ("start_date", "due_date", "end_date"))
        if quantity < 1 or due < start or end < start:
            raise ValueError("quantity must be >= 1 and due/end dates must not precede start_date")
        defects = max(0, min(quantity, int(data.get("defective_units", 0))))
    except (TypeError, ValueError) as exc:
        return error("validation_error", str(exc))
    artisan = None
    if data.get("artisan_id"):
        artisan = Employee.objects.select_related("department").filter(pk=data["artisan_id"]).first()
        if artisan is None:
            return error("validation_error", "Unknown artisan.", details={"artisan_id": "not found"})
    prof = Feat.product_profile(product)
    a = Feat.artisan_profile(artisan)
    actual = float(data.get("actual_days") or max(0.5, (end - start).days))
    allotted = max(1, (due - start).days)
    rec = ProductionRecord.objects.create(
        product=product, artisan=artisan, product_code=product.code, product_name=product.name,
        category=product.category, quantity=quantity, unit_price=prof["unit_price"],
        material_cost_per_unit=prof["material_cost_per_unit"], bom_items=prof["bom_items"],
        bom_qty_per_unit=prof["bom_qty_per_unit"],
        standard_days=Feat.standard_days(product.category, quantity, prof["bom_items"], prof["bom_qty_per_unit"]),
        allotted_days=allotted, artisan_name=a["artisan_name"], artisan_contract=a["artisan_contract"],
        artisan_department=a["artisan_department"],
        dept_match=Feat.department_matches(product.category, a["artisan_department"]),
        artisan_workload=_int(data.get("artisan_workload"), 0, 0, 50),
        stock_coverage=float(data.get("stock_coverage") or Feat.STOCK_COVERAGE_CAP),
        start_date=start, due_date=due, end_date=end, actual_days=actual, delayed=actual > allotted,
        defective_units=defects, source="api",
    )
    Feat.invalidate_history_cache()
    return ok(S.record_to_dict(rec), status=201)


# ---------------------------------------------------------------- incoming orders (new data + live scoring)
@api_endpoint(methods=("GET", "POST"))
def orders(request):
    if request.method == "GET":
        qs = IncomingOrder.objects.select_related("product", "recommended_artisan", "requested_artisan")
        if request.GET.get("status"):
            qs = qs.filter(status__iexact=request.GET["status"])
        if request.GET.get("risk"):
            qs = qs.filter(risk_level__iexact=request.GET["risk"])
        if request.GET.get("since_id"):
            qs = qs.filter(pk__gt=_int(request.GET["since_id"], 0, 0))
        limit = _int(request.GET.get("limit"), 20, 1, 200)
        items = list(qs[:limit])
        return ok([S.order_to_dict(o) for o in items], count=len(items),
                  latest_id=items[0].pk if items else None)
    try:
        payload = read_json(request)
    except ValueError as exc:
        return error("invalid_json", f"Invalid JSON body: {exc}")
    try:
        order = service.ingest_order(payload, user=request.api_user,
                                     source=str(payload.get("source") or "api")[:30])
    except OrderValidationError as exc:
        return error("validation_error", "The order is not valid.", details=exc.errors)
    except ModelUnavailable as exc:
        return error("model_unavailable", str(exc), 503)
    return ok(S.order_to_dict(order), status=201)


@api_endpoint()
def order_detail(request, pk):
    order = IncomingOrder.objects.filter(pk=pk).first()
    if order is None:
        return error("not_found", f"Order {pk} not found.", 404)
    return ok({**S.order_to_dict(order), "full_prediction": order.prediction})


# ---------------------------------------------------------------- stateless prediction
@api_endpoint(methods=("POST",), staff_methods=())
def predict(request):
    try:
        data = read_json(request)
        clean = service.validate_order_payload(data)
    except ValueError as exc:
        if isinstance(exc, OrderValidationError):
            return error("validation_error", "Invalid input.", details=exc.errors)
        return error("invalid_json", f"Invalid JSON body: {exc}")
    try:
        result = service.predict_job(clean["product"], clean["quantity"], clean["due_date"],
                                     employee=clean["employee"])
    except ModelUnavailable as exc:
        return error("model_unavailable", str(exc), 503)
    PredictionLog.objects.create(kind="api", object_ref=clean["product"].code, inputs=service.payload_safe(data),
                                 outputs=service._slim(result), model_version=result["model_version"],
                                 user=request.api_user)
    return ok(result)


# ---------------------------------------------------------------- model registry
@api_endpoint()
def model_info(request):
    active = MLModelVersion.objects.filter(is_active=True)
    history = MLModelVersion.objects.all()[:20]
    return ok({"active": [S.model_version_to_dict(m) for m in active],
               "history": [{"name": m.name, "version": m.version, "algorithm": m.algorithm,
                            "trained_at": m.trained_at.isoformat(), "metrics": m.metrics} for m in history],
               "status": predictor.status()})


@api_endpoint(methods=("POST",))
def model_retrain(request):
    try:
        summary = train_models(trained_by=f"API: {request.api_user.username}")
    except TrainingError as exc:
        return error("training_failed", str(exc), 409)
    return ok(summary, status=201)


# ---------------------------------------------------------------- analytics
@api_endpoint()
def dashboard_summary(request):
    return ok({
        "kpis": insights.history_kpis(),
        "inventory_value_rwf": insights.inventory_value(),
        "task_status": insights.task_status_breakdown(),
        "monthly_trend": insights.monthly_trend(),
        "category_delay": insights.category_delay(),
    })


@api_endpoint()
def material_forecast(request):
    return ok(insights.material_demand_forecast())


@api_endpoint()
def fx_rate(request):
    data = fetch_usd_rwf(force=request.GET.get("refresh") in ("1", "true"))
    value = insights.inventory_value()
    data = {**data, "inventory_value_rwf": value,
            "inventory_value_usd": round(value / data["rate"], 2) if data.get("rate") else None}
    return ok(data)
