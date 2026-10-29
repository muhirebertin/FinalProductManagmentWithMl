# analytics/signals.py
"""
Continuous-learning loop: whenever a real ProductionTask is marked
'Completed', its real outcome is copied into ProductionRecord (source='live').
The next retraining therefore learns from real factory data as well as the
synthetic history. Any error is logged and never blocks saving the task.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from production.models import ProductionTask

logger = logging.getLogger("analytics")


def record_from_task(task):
    """Create (once) the ProductionRecord for a completed task. Returns it or None."""
    from .ml import features as F
    from .models import ProductionRecord

    if task.status != "Completed" or task.product is None:
        return None
    if ProductionRecord.objects.filter(task=task).exists():
        return None
    created = timezone.localtime(task.created_at) if task.created_at else timezone.localtime()
    start = created.date()
    now = timezone.localtime()
    actual = max(0.5, round((now - created).total_seconds() / 86400.0, 1))
    end = max(start, now.date())
    allotted = max(1, (task.due_date - start).days)
    prof = F.product_profile(task.product)
    a = F.artisan_profile(task.assigned_to)
    rec = ProductionRecord.objects.create(
        product=task.product, artisan=task.assigned_to, task=task,
        product_code=prof["product_code"], product_name=prof["product_name"], category=prof["category"],
        quantity=task.target_quantity, unit_price=prof["unit_price"],
        material_cost_per_unit=prof["material_cost_per_unit"], bom_items=prof["bom_items"],
        bom_qty_per_unit=prof["bom_qty_per_unit"],
        standard_days=F.standard_days(prof["category"], task.target_quantity, prof["bom_items"],
                                      prof["bom_qty_per_unit"]),
        allotted_days=allotted, artisan_name=a["artisan_name"], artisan_contract=a["artisan_contract"],
        artisan_department=a["artisan_department"],
        dept_match=F.department_matches(prof["category"], a["artisan_department"]),
        artisan_workload=F.artisan_workload(task.assigned_to, exclude_task_id=task.pk),
        stock_coverage=F.STOCK_COVERAGE_CAP,
        start_date=start, due_date=task.due_date, end_date=end, actual_days=actual,
        delayed=end > task.due_date, defective_units=0, source="live",
    )
    F.invalidate_history_cache()
    return rec


@receiver(post_save, sender=ProductionTask, dispatch_uid="analytics_task_completed")
def on_task_saved(sender, instance, **kwargs):
    if kwargs.get("raw"):
        return
    try:
        record_from_task(instance)
    except Exception:  # analytics must never break the core workflow
        logger.exception("Could not create a ProductionRecord for task %s", instance.pk)
