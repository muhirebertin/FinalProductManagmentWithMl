# analytics/apps.py
from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """
    AI & Analytics extension for the Le Mieux Production Management System.

    Provides:
      * a versioned REST-style JSON API (/api/v1/)
      * historical production records used as training data
      * machine-learning models (delay-risk classifier + duration regressor)
      * real-time scoring of incoming orders and open production tasks
      * Open API integration (live USD/RWF exchange rate)
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "analytics"
    verbose_name = "AI & Analytics"

    def ready(self):
        # Connect signal handlers (completed tasks feed the training dataset).
        from . import signals  # noqa: F401
