# production/views.py
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, F
from .models import ProductionTask
from .forms import ProductionTaskForm
from employees.models import Employee
from inventory.models import RawMaterial, Product


def is_staff_check(user):
    return user.is_staff # The security check


@login_required
def dashboard(request):
    total_artisans = Employee.objects.filter(is_active=True).count()
    total_tasks = ProductionTask.objects.count()
    pending_tasks = ProductionTask.objects.filter(status='Pending').count()
    completed_tasks = ProductionTask.objects.filter(status='Completed').count()

    recent_tasks = ProductionTask.objects.select_related('assigned_to', 'product').order_by('-created_at')[:5]
    low_stock_materials = RawMaterial.objects.filter(quantity_in_stock__lte=F('reorder_level'))

    # Find overdue tasks using our custom property
    open_tasks = ProductionTask.objects.exclude(status='Completed')
    overdue_tasks = [task for task in open_tasks if task.is_overdue]

    alert_count = low_stock_materials.count() + len(overdue_tasks)

    top_artisans = Employee.objects.filter(is_active=True).annotate(
        active_tasks=Count(
            'tasks',
            filter=Q(tasks__status__in=['Pending', 'In Progress'])
        )
    ).order_by('-active_tasks')[:5]

    context = {
        'total_artisans': total_artisans,
        'total_tasks': total_tasks,
        'pending_tasks': pending_tasks,
        'completed_tasks': completed_tasks,
        'recent_tasks': recent_tasks,
        'low_stock_materials': low_stock_materials,
        'overdue_tasks': overdue_tasks,
        'alert_count': alert_count,
        'top_artisans': top_artisans,
    }

    # AI & Analytics extension: extra widgets (charts, risk monitor, live orders).
    # Wrapped defensively so the original dashboard always renders.
    try:
        from analytics.dashboard import dashboard_context
        context.update(dashboard_context())
    except Exception:
        context['ai_enabled'] = False

    return render(request, 'dashboard.html', context)


@login_required
def task_list(request):
    tasks = ProductionTask.objects.all().select_related('assigned_to')
    return render(request, 'production/task_list.html', {'tasks': tasks})

@login_required
@user_passes_test(is_staff_check, login_url='/')
def task_create(request):
    if request.method == 'POST':
        form = ProductionTaskForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('production:task_list')
    else:
        form = ProductionTaskForm()
    return render(request, 'production/task_form.html', {'form': form, 'title': 'Assign New Task'})

@login_required
def task_detail(request, pk):
    task = get_object_or_404(ProductionTask, pk=pk)
    return render(request, 'production/task_detail.html', {'task': task})

@login_required
@user_passes_test(is_staff_check, login_url='/')
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

@login_required
@user_passes_test(is_staff_check, login_url='/')
def task_delete(request, pk):
    task = get_object_or_404(ProductionTask, pk=pk)
    if request.method == 'POST':
        task.delete()
        return redirect('production:task_list')
    return render(request, 'production/task_confirm_delete.html', {'task': task})


@login_required
def system_alerts(request):
    from inventory.models import RawMaterial
    from django.db.models import F

    low_stock_materials = RawMaterial.objects.filter(quantity_in_stock__lte=F('reorder_level'))
    open_tasks = ProductionTask.objects.exclude(status='Completed')
    overdue_tasks = [task for task in open_tasks if task.is_overdue]

    return render(request, 'production/alerts.html', {
        'low_stock_materials': low_stock_materials,
        'overdue_tasks': overdue_tasks,
    })

@login_required
def material_list(request):
    materials = RawMaterial.objects.all()
    return render(request, 'inventory/material_list.html', {'materials': materials})

@login_required
def product_list(request):
    products = Product.objects.all()
    return render(request, 'inventory/product_list.html', {'products': products})