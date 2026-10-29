# analytics/dashboard.py
"""
Extra context for the main dashboard (production.views.dashboard).

Everything is computed defensively: if anything in the AI layer fails, the
dashboard still renders all of its original widgets and shows a small
notice instead of the AI widgets.
"""
import logging

from .ml import insights
from .ml.service import predictor, score_open_tasks
from .models import IncomingOrder, MLModelVersion

logger = logging.getLogger("analytics")


def dashboard_context():
    ctx = {"ai_enabled": True}
    try:
        predictor.models()  # loads models; self-heals (retrains) if needed
        scored = score_open_tasks()
        ctx["risk_tasks"] = scored
        ctx["risk_counts"] = {
            level: sum(1 for _, r in scored if r.get("risk_level") == level) for level in ("High", "Medium", "Low")
        }
        ctx["at_risk_count"] = ctx["risk_counts"]["High"]
        active = {m.name: m for m in MLModelVersion.objects.filter(is_active=True)}
        ctx["model_classifier"] = active.get("delay_classifier")
        ctx["model_regressor"] = active.get("duration_regressor")
        ctx["ai_ready"] = True
    except Exception as exc:
        logger.exception("AI engine unavailable on dashboard")
        ctx["ai_ready"] = False
        ctx["ai_error"] = str(exc)

    try:
        kpis = insights.history_kpis()
        ctx["kpis"] = kpis
        ctx["inventory_value"] = insights.inventory_value()
        ctx["latest_orders"] = list(IncomingOrder.objects.select_related(
            "product", "recommended_artisan", "requested_artisan")[:8])
        ctx["latest_order_id"] = ctx["latest_orders"][0].pk if ctx["latest_orders"] else 0
        forecast = insights.material_demand_forecast()
        ctx["forecast"] = forecast[:6]
        ctx["forecast_issues"] = sum(1 for f in forecast if f["status"] != "ok")
        ctx["ai_charts"] = {
            "status": insights.task_status_breakdown(),
            "trend": insights.monthly_trend(12),
            "category": insights.category_delay(),
            "risk": [ctx.get("risk_counts", {}).get(k, 0) for k in ("High", "Medium", "Low")],
        }
    except Exception as exc:
        logger.exception("Analytics widgets unavailable on dashboard")
        ctx["analytics_error"] = str(exc)
    return ctx
