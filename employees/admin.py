# employees/admin.py
from django.contrib import admin
from .models import Department, Employee, Contract, LeaveRequest

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'department', 'hire_date', 'is_active')
    list_filter = ('department', 'is_active')
    search_fields = ('first_name', 'last_name')

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('employee', 'contract_type', 'start_date', 'end_date', 'base_salary', 'is_active')
    list_filter = ('contract_type', 'is_active')
    search_fields = ('employee__first_name', 'employee__last_name')

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'status')
    list_filter = ('status', 'leave_type')
    search_fields = ('employee__first_name', 'employee__last_name')
    list_editable = ('status',)