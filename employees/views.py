# employees/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Employee, Contract, LeaveRequest
from .forms import EmployeeForm, ContractForm, LeaveRequestForm

# Create a simple rule: Is the user a staff member?
def is_hr_staff(user):
    return user.is_staff

# Stack the decorators! They must be logged in AND pass the HR test.
# If they fail the HR test, we kick them back to the dashboard ('/').
@login_required
@user_passes_test(is_hr_staff, login_url='/')
def employee_list(request):
    employees = Employee.objects.all().select_related('department')
    return render(request, 'employees/employee_list.html', {'employees': employees})

@login_required
@user_passes_test(is_hr_staff, login_url='/')
def employee_create(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('employees:employee_list')
    else:
        form = EmployeeForm()
    return render(request, 'employees/employee_form.html', {'form': form, 'title': 'Add New Artisan'})

@login_required
@user_passes_test(is_hr_staff, login_url='/')
def employee_detail(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    # Fetch related contracts and leaves using the related_names we defined in models.py
    contracts = employee.contracts.all().order_by('-start_date')
    leaves = employee.leave_requests.all().order_by('-applied_on')

    return render(request, 'employees/employee_detail.html', {
        'employee': employee,
        'contracts': contracts,
        'leaves': leaves
    })

@login_required
@user_passes_test(is_hr_staff, login_url='/')
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

@login_required
@user_passes_test(is_hr_staff, login_url='/')
def employee_delete(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        employee.delete()
        return redirect('employees:employee_list')
    return render(request, 'employees/employee_confirm_delete.html', {'employee': employee})


@login_required
@user_passes_test(is_hr_staff, login_url='/')
def update_leave_status(request, leave_id, status):
    leave = get_object_or_404(LeaveRequest, id=leave_id)

    # Security check to ensure URLs aren't manipulated
    if status in ['Approved', 'Rejected', 'Pending']:
        leave.status = status
        leave.save()

    # Redirect back to the employee's profile after clicking Approve/Reject
    return redirect('employees:employee_detail', pk=leave.employee.id)


@login_required
@user_passes_test(is_hr_staff, login_url='/')
def contract_create(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)
    if request.method == 'POST':
        form = ContractForm(request.POST)
        if form.is_valid():
            # commit=False allows us to attach the employee before saving
            contract = form.save(commit=False)
            contract.employee = employee
            contract.save()
            return redirect('employees:employee_detail', pk=employee.id)
    else:
        form = ContractForm()

    return render(request, 'employees/hr_action_form.html', {
        'form': form,
        'title': f'Assign Contract to {employee.first_name} {employee.last_name}',
        'employee': employee
    })


@login_required
@user_passes_test(is_hr_staff, login_url='/')
def leave_create(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.employee = employee
            # HR is logging this, so it defaults to Pending until they explicitly hit Approve
            leave.save()
            return redirect('employees:employee_detail', pk=employee.id)
    else:
        form = LeaveRequestForm()

    return render(request, 'employees/hr_action_form.html', {
        'form': form,
        'title': f'Log Leave for {employee.first_name} {employee.last_name}',
        'employee': employee
    })