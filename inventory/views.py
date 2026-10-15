# inventory/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import ProtectedError
from django.contrib import messages
from .models import RawMaterial, Product
from .forms import RawMaterialForm, ProductForm, BOMForm, BOMFormSet


def is_staff_check(user):
    return user.is_staff


# ==========================================
# RAW MATERIAL VIEWS
# ==========================================

@login_required
def material_list(request):
    materials = RawMaterial.objects.all()
    return render(request, 'inventory/material_list.html', {'materials': materials})


@login_required
def material_detail(request, pk):
    material = get_object_or_404(RawMaterial, pk=pk)
    return render(request, 'inventory/material_detail.html', {'material': material})


@login_required
@user_passes_test(is_staff_check, login_url='/')
def material_create(request):
    if request.method == 'POST':
        form = RawMaterialForm(request.POST)
        if form.is_valid():
            material = form.save()
            messages.success(request, f"Raw Material '{material.name}' added successfully.")
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
            messages.success(request, f"Raw Material '{material.name}' updated successfully.")
            return redirect('inventory:material_list')
    else:
        form = RawMaterialForm(instance=material)
    return render(request, 'inventory/material_form.html', {'form': form, 'title': 'Edit Material'})


@login_required
@user_passes_test(is_staff_check, login_url='/')
def material_delete(request, pk):
    material = get_object_or_404(RawMaterial, pk=pk)
    if request.method == 'POST':
        try:
            material.delete()
            messages.success(request, f"Raw Material '{material.name}' was successfully deleted.")
            return redirect('inventory:material_list')
        except ProtectedError:
            messages.error(
                request,
                f"Cannot delete '{material.name}' because it is used in a product's bill of materials. Remove it from the product recipes first."
            )
            return redirect('inventory:material_detail', pk=material.id)

    return render(request, 'confirm_delete.html', {
        'object': material,
        'title': f"Delete Raw Material: {material.name}",
        'cancel_url': 'inventory:material_detail'
    })


# ==========================================
# PRODUCT VIEWS
# ==========================================

@login_required
def product_list(request):
    products = Product.objects.all()
    return render(request, 'inventory/product_list.html', {'products': products})


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    boms = product.bom_items.all()

    bom_data = []
    total_production_cost = 0

    # Calculate costs dynamically
    for bom in boms:
        cost = bom.quantity_per_unit * bom.material.unit_cost
        total_production_cost += cost
        bom_data.append({
            'bom_id': bom.id,
            'material': bom.material,
            'quantity': bom.quantity_per_unit,
            'unit_cost': bom.material.unit_cost,
            'total_cost': cost
        })

    # Calculate predicted profit margin
    profit = product.unit_price - total_production_cost

    return render(request, 'inventory/product_detail.html', {
        'product': product,
        'bom_data': bom_data,
        'total_production_cost': total_production_cost,
        'profit': profit
    })


@login_required
@user_passes_test(is_staff_check, login_url='/')
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        formset = BOMFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            product = form.save()
            formset.instance = product
            formset.save()
            messages.success(request, f"Product '{product.name}' and its recipe were created successfully.")
            return redirect('inventory:product_detail', pk=product.id)
    else:
        form = ProductForm()
        formset = BOMFormSet()

    return render(request, 'inventory/product_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Add New Product & Recipe'
    })


@login_required
@user_passes_test(is_staff_check, login_url='/')
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        formset = BOMFormSet(request.POST, instance=product)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"Product '{product.name}' and its recipe were updated successfully.")
            return redirect('inventory:product_detail', pk=product.id)
    else:
        form = ProductForm(instance=product)
        formset = BOMFormSet(instance=product)

    return render(request, 'inventory/product_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Edit Product & Recipe'
    })


@login_required
@user_passes_test(is_staff_check, login_url='/')
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == 'POST':
        try:
            product.delete()
            messages.success(request, f"Product '{product.name}' was successfully deleted.")
            return redirect('inventory:product_list')
        except ProtectedError:
            messages.error(
                request,
                f"Cannot delete '{product.name}' because it is assigned to active production tasks. Please delete those tasks first."
            )
            return redirect('inventory:product_detail', pk=product.id)

    return render(request, 'confirm_delete.html', {
        'object': product,
        'title': f"Delete Product: {product.name}",
        'cancel_url': 'inventory:product_detail'
    })