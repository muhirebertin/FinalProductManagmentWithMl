# employees/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Employee
from .forms import EmployeeForm


@login_required(login_url='/admin/login/')
def employee_list(request):
    employees = Employee.objects.all().select_related('department')
    return render(request, 'employees/employee_list.html', {'employees': employees})


@login_required(login_url='/admin/login/')
def employee_create(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('employees:employee_list')
    else:
        form = EmployeeForm()

    # We pass a title so the same form template works for Create and Update
    return render(request, 'employees/employee_form.html', {'form': form, 'title': 'Add New Artisan'})


@login_required(login_url='/admin/login/')
def employee_detail(request, pk):
    # This satisfies the "individual record details" requirement
    employee = get_object_or_404(Employee, pk=pk)
    return render(request, 'employees/employee_detail.html', {'employee': employee})


@login_required(login_url='/admin/login/')
def employee_update(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            return redirect('employees:employee_list')
    else:
        form = EmployeeForm(instance=employee)

    return render(request, 'employees/employee_form.html', {'form': form, 'title': 'Edit Artisan'})


@login_required(login_url='/admin/login/')
def employee_delete(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        # This executes only after they click "Yes" on the confirmation page
        employee.delete()
        return redirect('employees:employee_list')
    # If it's a GET request, we show the confirmation page
    return render(request, 'employees/employee_confirm_delete.html', {'employee': employee})