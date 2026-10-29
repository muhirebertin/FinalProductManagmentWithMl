# analytics/admin.py
from django.contrib import admin

from .models import APIKey, ExternalDataSnapshot, IncomingOrder, MLModelVersion, PredictionLog, ProductionRecord


@admin.register(ProductionRecord)
class ProductionRecordAdmin(admin.ModelAdmin):
    list_display = ("product_code", "category", "quantity", "artisan_name", "start_date", "allotted_days",
                    "actual_days", "delayed", "source")
    list_filter = ("source", "category", "delayed", "artisan_contract")
    search_fields = ("product_code", "product_name", "artisan_name")
    date_hierarchy = "start_date"


@admin.register(IncomingOrder)
class IncomingOrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "product_code", "quantity", "due_date", "risk_level", "delay_probability",
                    "predicted_days", "recommended_artisan", "status", "received_at")
    list_filter = ("status", "risk_level", "channel", "source")
    search_fields = ("reference", "customer", "product_code")
    readonly_fields = ("prediction",)


@admin.register(MLModelVersion)
class MLModelVersionAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "algorithm", "is_active", "n_train", "n_test", "trained_at", "trained_by")
    list_filter = ("name", "is_active", "algorithm")


@admin.register(PredictionLog)
class PredictionLogAdmin(admin.ModelAdmin):
    list_display = ("kind", "object_ref", "model_version", "user", "created_at")
    list_filter = ("kind",)


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "prefix", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active",)
    readonly_fields = ("prefix", "hashed_key", "created_at", "last_used_at")


@admin.register(ExternalDataSnapshot)
class ExternalDataSnapshotAdmin(admin.ModelAdmin):
    list_display = ("key", "fetched_at")
