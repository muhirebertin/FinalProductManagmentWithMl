# production/admin.py
from django.contrib import admin
from .models import ProductionTask

@admin.register(ProductionTask)
class ProductionTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'assigned_to', 'status', 'due_date')
    list_filter = ('status', 'due_date')
    search_fields = ('title', 'description')