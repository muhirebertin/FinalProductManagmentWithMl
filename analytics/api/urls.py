# analytics/api/urls.py  -> mounted at /api/v1/
from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("", views.api_index, name="index"),
    path("health/", views.health, name="health"),
    path("products/", views.products, name="products"),
    path("materials/", views.materials, name="materials"),
    path("employees/", views.employees, name="employees"),
    path("tasks/", views.tasks, name="tasks"),
    path("tasks/<int:pk>/prediction/", views.task_prediction, name="task_prediction"),
    path("records/", views.records, name="records"),
    path("orders/", views.orders, name="orders"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("predict/", views.predict, name="predict"),
    path("model/", views.model_info, name="model"),
    path("model/retrain/", views.model_retrain, name="model_retrain"),
    path("dashboard/summary/", views.dashboard_summary, name="dashboard_summary"),
    path("forecast/materials/", views.material_forecast, name="material_forecast"),
    path("external/fx/", views.fx_rate, name="fx_rate"),
]
