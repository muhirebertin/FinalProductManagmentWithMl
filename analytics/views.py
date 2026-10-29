# analytics/views.py
"""Web pages of the AI & Analytics module."""
import logging
import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from production.forms import ProductionTaskForm

from .forms import APIKeyForm, PredictionForm
from .ml import insights, service
from .ml.service import ModelUnavailable, OrderValidationError, predictor
from .ml.synthetic import random_order_payload
from .ml.training import TrainingError, train_models
from .models import APIKey, IncomingOrder, MLModelVersion, PredictionLog, ProductionRecord

logger = logging.getLogger("analytics")


def is_staff_check(user):
    return user.is_staff


def _safe_next(request, default):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return default


# ---------------------------------------------------------------------------
# AI Insights: incoming orders + open-task risk monitor
# ---------------------------------------------------------------------------
@login_required
def insights_view(request):
    orders = IncomingOrder.objects.select_related("product", "recommended_artisan", "requested_artisan",
                                                  "converted_task")
    status = request.GET.get("status", "New")
    risk = request.GET.get("risk", "")
    if status in dict(IncomingOrder.STATUS_CHOICES):
        orders = orders.filter(status=status)
    else:
        status = "All"
    if risk in ("Low", "Medium", "High"):
        orders = orders.filter(risk_level=risk)
    page = Paginator(orders, 15).get_page(request.GET.get("page"))

    risk_tasks, ai_error = [], None
    try:
        risk_tasks = service.score_open_tasks()
    except Exception as exc:
        logger.exception("Risk monitor failed")
        ai_error = str(exc)

    counts = IncomingOrder.objects.aggregate(
        new=Count("id", filter=Q(status="New")),
        high=Count("id", filter=Q(status="New", risk_level="High")),
        converted=Count("id", filter=Q(status="Converted")),
        total=Count("id"))
    return render(request, "analytics/insights.html", {
        "page": page, "status": status, "risk": risk, "counts": counts,
        "risk_tasks": risk_tasks, "ai_error": ai_error,
        "forecast": insights.material_demand_forecast(),
        "status_choices": ["New", "Converted", "Dismissed", "All"],
    })


@login_required
def order_detail(request, pk):
    order = get_object_or_404(IncomingOrder.objects.select_related("product", "converted_task"), pk=pk)
    return render(request, "analytics/order_detail.html", {"order": order, "p": order.prediction or {}})


@login_required
@user_passes_test(is_staff_check, login_url="/")
def order_convert(request, pk):
    """Turn an AI-scored order into a real ProductionTask (all original validation rules apply)."""
    order = get_object_or_404(IncomingOrder.objects.select_related("product"), pk=pk)
    if order.status == "Converted" and order.converted_task_id:
        messages.info(request, f"Order {order.reference} has already been converted.")
        return redirect("production:task_detail", pk=order.converted_task_id)
    if order.product is None:
        messages.error(request, "This order's product no longer exists.")
        return redirect("analytics:insights")

    p = order.prediction or {}
    initial = {
        "title": f"{order.product.name} x{order.quantity} - {order.reference}"[:200],
        "product": order.product.pk,
        "target_quantity": order.quantity,
        "produced_quantity": 0,
        "assigned_to": order.assigned_artisan.pk if order.assigned_artisan else None,
        "status": "Pending",
        "due_date": order.due_date,
        "description": (f"Created from incoming order {order.reference} ({order.channel}"
                        f"{', ' + order.customer if order.customer else ''}). "
                        f"AI forecast: {order.delay_percent}% delay risk ({order.risk_level}), "
                        f"~{order.predicted_days} days expected."
                        + (f" {p['recommendations'][0]}" if p.get("recommendations") else "")),
    }
    if request.method == "POST":
        form = ProductionTaskForm(request.POST)
        if form.is_valid():
            task = form.save()
            order.status = "Converted"
            order.converted_task = task
            order.save(update_fields=["status", "converted_task"])
            messages.success(request, f"Order {order.reference} converted into production task TSK-{task.pk}. "
                                      f"Materials were reserved from the warehouse.")
            return redirect("production:task_detail", pk=task.pk)
    else:
        form = ProductionTaskForm(initial=initial)
    return render(request, "production/task_form.html",
                  {"form": form, "title": f"Create Task from Incoming Order {order.reference}"})


@login_required
@user_passes_test(is_staff_check, login_url="/")
@require_POST
def order_dismiss(request, pk):
    order = get_object_or_404(IncomingOrder, pk=pk)
    if order.status == "New":
        order.status = "Dismissed"
        order.save(update_fields=["status"])
        messages.warning(request, f"Order {order.reference} dismissed.")
    return redirect(_safe_next(request, reverse("analytics:insights")))


@login_required
@user_passes_test(is_staff_check, login_url="/")
@require_POST
def simulate_orders(request):
    """Generate N realistic incoming orders through the same pipeline as the API."""
    try:
        count = max(1, min(10, int(request.POST.get("count", 3))))
    except ValueError:
        count = 3
    rnd = random.Random()
    created = []
    try:
        for _ in range(count):
            created.append(service.ingest_order(random_order_payload(rnd), user=request.user, source="simulator"))
        high = sum(1 for o in created if o.risk_level == "High")
        messages.success(request, f"{len(created)} incoming order(s) received and scored by the AI engine"
                                  + (f" - {high} flagged HIGH risk." if high else "."))
    except (ModelUnavailable, OrderValidationError, ValueError) as exc:
        messages.error(request, f"Simulation failed: {exc}")
    return redirect(_safe_next(request, reverse("analytics:insights")))


# ---------------------------------------------------------------------------
# What-if predictor
# ---------------------------------------------------------------------------
@login_required
def predictor_view(request):
    result = None
    form = PredictionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        if request.POST.get("action") == "submit_order":
            if not request.user.is_staff:
                messages.error(request, "Only managers can submit orders.")
                return redirect("analytics:predictor")
            payload = {"product_code": cd["product"].code, "quantity": cd["quantity"],
                       "due_date": cd["due_date"].isoformat(), "customer": cd["customer"],
                       "channel": cd["channel"], "artisan_id": cd["artisan"].pk if cd["artisan"] else None}
            try:
                order = service.ingest_order(payload, user=request.user, source="web")
                messages.success(request, f"Order {order.reference} submitted and scored "
                                          f"({order.risk_level} risk).")
                return redirect("analytics:order_detail", pk=order.pk)
            except (OrderValidationError, ModelUnavailable) as exc:
                messages.error(request, str(exc))
        else:
            try:
                result = service.predict_job(cd["product"], cd["quantity"], cd["due_date"], employee=cd["artisan"])
                PredictionLog.objects.create(
                    kind="whatif", object_ref=cd["product"].code,
                    inputs={"product": cd["product"].code, "quantity": cd["quantity"],
                            "due_date": cd["due_date"].isoformat(),
                            "artisan": cd["artisan"].pk if cd["artisan"] else None},
                    outputs=service._slim(result), model_version=result["model_version"], user=request.user)
            except ModelUnavailable as exc:
                messages.error(request, f"The AI engine is not available: {exc}")
    return render(request, "analytics/predictor.html", {"form": form, "result": result})


# ---------------------------------------------------------------------------
# Model Center
# ---------------------------------------------------------------------------
@login_required
def model_center(request):
    active = {m.name: m for m in MLModelVersion.objects.filter(is_active=True)}
    history = MLModelVersion.objects.all()[:30]
    sources = dict(ProductionRecord.objects.values_list("source").annotate(c=Count("id")).values_list("source", "c"))
    return render(request, "analytics/model_center.html", {
        "clf": active.get("delay_classifier"), "reg": active.get("duration_regressor"),
        "history": history, "status": predictor.status(), "sources": sources,
        "record_total": sum(sources.values()),
        "recent_predictions": PredictionLog.objects.select_related("user")[:10],
        "prediction_total": PredictionLog.objects.count(),
    })


@login_required
@user_passes_test(is_staff_check, login_url="/")
@require_POST
def model_retrain(request):
    try:
        summary = train_models(trained_by=request.user.username)
        c, r = summary["delay_classifier"], summary["duration_regressor"]
        messages.success(
            request,
            f"Models retrained on {summary['records']} records in {summary['seconds']}s. "
            f"Classifier v{c['version']} ({c['algorithm']}, ROC-AUC {c['metrics']['roc_auc']}); "
            f"Regressor v{r['version']} ({r['algorithm']}, MAE {r['metrics']['mae']} days).")
    except TrainingError as exc:
        messages.error(request, f"Training failed: {exc}")
    return redirect("analytics:model_center")


# ---------------------------------------------------------------------------
# Production history (training data browser)
# ---------------------------------------------------------------------------
@login_required
def history_view(request):
    qs = ProductionRecord.objects.all()
    source = request.GET.get("source", "")
    if source in dict(ProductionRecord.SOURCE_CHOICES):
        qs = qs.filter(source=source)
    records = qs.order_by("-start_date", "-id")[:1000]
    return render(request, "analytics/history.html", {
        "records": records, "source": source, "total": qs.count(),
        "source_choices": ProductionRecord.SOURCE_CHOICES,
        "category_stats": insights.category_delay(),
    })


# ---------------------------------------------------------------------------
# API Center (documentation + key management)
# ---------------------------------------------------------------------------
@login_required
def api_center(request):
    form = APIKeyForm(request.POST or None)
    if request.method == "POST":
        if not request.user.is_staff:
            messages.error(request, "Only managers can create API keys.")
            return redirect("analytics:api_center")
        if form.is_valid():
            key, raw = APIKey.generate(request.user, form.cleaned_data["name"])
            request.session["new_api_key"] = raw
            messages.success(request, f"API key '{key.name}' created. Copy it now - it will not be shown again.")
            return redirect("analytics:api_center")
    new_key = request.session.pop("new_api_key", None)
    keys = APIKey.objects.select_related("user").all() if request.user.is_staff else APIKey.objects.none()
    base = request.build_absolute_uri("/").rstrip("/")
    return render(request, "analytics/api_center.html",
                  {"form": form, "keys": keys, "new_key": new_key, "base_url": base})


@login_required
@user_passes_test(is_staff_check, login_url="/")
@require_POST
def api_key_revoke(request, pk):
    key = get_object_or_404(APIKey, pk=pk)
    key.is_active = False
    key.save(update_fields=["is_active"])
    messages.warning(request, f"API key '{key.name}' revoked.")
    return redirect("analytics:api_center")
