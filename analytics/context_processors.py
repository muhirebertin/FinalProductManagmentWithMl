# analytics/context_processors.py
"""Makes the live alert count available to every page (navbar bell)."""
import logging

from django.db.models import F

logger = logging.getLogger("analytics")


def nav_alerts(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    try:
        from analytics.models import IncomingOrder
        from inventory.models import RawMaterial
        from production.models import ProductionTask

        low_stock = RawMaterial.objects.filter(quantity_in_stock__lte=F("reorder_level")).count()
        # Note: no .only() here - ProductionTask.__init__ reads fields, so deferred loading would recurse.
        overdue = sum(1 for t in ProductionTask.objects.exclude(status="Completed") if t.is_overdue)
        high_risk = IncomingOrder.objects.filter(status="New", risk_level="High").count()
        return {"nav_alerts": {"low_stock": low_stock, "overdue": overdue, "high_risk_orders": high_risk,
                               "total": low_stock + overdue + high_risk}}
    except Exception:  # e.g. before migrations have been applied
        logger.debug("nav_alerts unavailable", exc_info=True)
        return {"nav_alerts": {"low_stock": 0, "overdue": 0, "high_risk_orders": 0, "total": 0}}
