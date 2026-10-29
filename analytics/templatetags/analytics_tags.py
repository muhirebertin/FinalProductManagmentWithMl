# analytics/templatetags/analytics_tags.py
import logging

from django import template

register = template.Library()
logger = logging.getLogger("analytics")

RISK_BADGE = {"High": "danger", "Medium": "warning", "Low": "success", "Overdue": "danger"}


@register.simple_tag
def task_risk(task):
    """{% task_risk task as ai %} -> AI assessment dict for a ProductionTask (never raises)."""
    try:
        from analytics.ml.service import score_task
        return score_task(task)
    except Exception as exc:
        logger.warning("task_risk failed for %s: %s", getattr(task, "pk", None), exc)
        return {"state": "error", "error": str(exc)}


@register.filter
def risk_badge(level):
    return RISK_BADGE.get(level or "", "secondary")


@register.filter
def pct(value):
    try:
        return f"{round(float(value) * 100)}%"
    except (TypeError, ValueError):
        return "-"


@register.filter
def rwf(value):
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return value


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None
