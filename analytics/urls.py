# analytics/urls.py  -> mounted at /analytics/
from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("insights/", views.insights_view, name="insights"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("orders/<int:pk>/convert/", views.order_convert, name="order_convert"),
    path("orders/<int:pk>/dismiss/", views.order_dismiss, name="order_dismiss"),
    path("orders/simulate/", views.simulate_orders, name="simulate_orders"),
    path("predict/", views.predictor_view, name="predictor"),
    path("models/", views.model_center, name="model_center"),
    path("models/retrain/", views.model_retrain, name="model_retrain"),
    path("history/", views.history_view, name="history"),
    path("api/", views.api_center, name="api_center"),
    path("api/keys/<int:pk>/revoke/", views.api_key_revoke, name="api_key_revoke"),
]
