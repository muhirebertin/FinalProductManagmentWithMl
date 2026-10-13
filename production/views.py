# production/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import ProductionTask
from .forms import ProductionTaskForm
from employees.models import Employee


@login_required(login_url='/admin/login/')
def dashboard(request):
    # Calculate live statistics from the database
    total_artisans = Employee.objects.filter(is_active=True).count()
    total_tasks = ProductionTask.objects.count()
    pending_tasks = ProductionTask.objects.filter(status='Pending').count()
    completed_tasks = ProductionTask.objects.filter(status='Completed').count()

    # Get the 5 most recent tasks for the data table
    recent_tasks = ProductionTask.objects.select_related('assigned_to').order_by('-created_at')[:5]

    context = {
        'total_artisans': total_artisans,
        'total_tasks': total_tasks,
        'pending_tasks': pending_tasks,
        'completed_tasks': completed_tasks,
        'recent_tasks': recent_tasks,
    }
    return render(request, 'dashboard.html', context)

@login_required(login_url='/admin/login/')
def task_list(request):
    tasks = ProductionTask.objects.all().select_related('assigned_to')
    return render(request, 'production/task_list.html', {'tasks': tasks})

@login_required(login_url='/admin/login/')
def task_create(request):
    if request.method == 'POST':
        form = ProductionTaskForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('production:task_list')
    else:
        form = ProductionTaskForm()
    return render(request, 'production/task_form.html', {'form': form, 'title': 'Assign New Task'})

@login_required(login_url='/admin/login/')
def task_detail(request, pk):
    task = get_object_or_404(ProductionTask, pk=pk)
    return render(request, 'production/task_detail.html', {'task': task})

@login_required(login_url='/admin/login/')
def task_update(request, pk):
    task = get_object_or_404(ProductionTask, pk=pk)
    if request.method == 'POST':
        form = ProductionTaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            return redirect('production:task_list')
    else:
        form = ProductionTaskForm(instance=task)
    return render(request, 'production/task_form.html', {'form': form, 'title': 'Edit Task'})

@login_required(login_url='/admin/login/')
def task_delete(request, pk):
    task = get_object_or_404(ProductionTask, pk=pk)
    if request.method == 'POST':
        task.delete()
        return redirect('production:task_list')
    return render(request, 'production/task_confirm_delete.html', {'task': task})