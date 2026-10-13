# inventory/admin.py
from django.contrib import admin
from .models import RawMaterial, Product, BillOfMaterial

@admin.register(RawMaterial)
class RawMaterialAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'quantity_in_stock', 'unit', 'reorder_level', 'unit_cost')
    search_fields = ('code', 'name')
    list_filter = ('unit',)

# TabularInline allows you to add materials directly on the Product page
class BillOfMaterialInline(admin.TabularInline):
    model = BillOfMaterial
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'unit_price')
    search_fields = ('code', 'name')
    list_filter = ('category',)
    inlines = [BillOfMaterialInline]