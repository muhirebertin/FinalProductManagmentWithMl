# inventory/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import RawMaterial, Product
from .forms import RawMaterialForm

def is_staff_check(user):
    return user.is_staff

@login_required
def material_list(request):
    materials = RawMaterial.objects.all()
    return render(request, 'inventory/material_list.html', {'materials': materials})

# Django is crashing because it cannot find this specific block below:
@login_required
def product_list(request):
    products = Product.objects.all()
    return render(request, 'inventory/product_list.html', {'products': products})

@login_required
@user_passes_test(is_staff_check, login_url='/')
def material_create(request):
    if request.method == 'POST':
        form = RawMaterialForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('inventory:material_list')
    else:
        form = RawMaterialForm()
    return render(request, 'inventory/material_form.html', {'form': form, 'title': 'Add New Material'})

@login_required
@user_passes_test(is_staff_check, login_url='/')
def material_update(request, pk):
    material = get_object_or_404(RawMaterial, pk=pk)
    if request.method == 'POST':
        form = RawMaterialForm(request.POST, instance=material)
        if form.is_valid():
            form.save()
            return redirect('inventory:material_list')
    else:
        form = RawMaterialForm(instance=material)
    return render(request, 'inventory/material_form.html', {'form': form, 'title': 'Edit Material'})

@login_required
@user_passes_test(is_staff_check, login_url='/')
def material_delete(request, pk):
    material = get_object_or_404(RawMaterial, pk=pk)
    if request.method == 'POST':
        material.delete()
        return redirect('inventory:material_list')
    return render(request, 'inventory/material_confirm_delete.html', {'item': material})

@login_required
def material_detail(request, pk):
    material = get_object_or_404(RawMaterial, pk=pk)
    return render(request, 'inventory/material_detail.html', {'material': material})