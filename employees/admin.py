# employees/admin.py
from django.contrib import admin
from .models import Department, Employee

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    # This makes the table show these specific columns
    list_display = ('first_name', 'last_name', 'department', 'hire_date', 'is_active')
    # This adds a filter box on the right side
    list_filter = ('department', 'is_active')
    search_fields = ('first_name', 'last_name')