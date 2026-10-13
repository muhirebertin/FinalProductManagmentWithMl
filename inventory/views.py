# inventory/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import RawMaterial, Product
from .forms import RawMaterialForm, ProductForm, BOMForm, BOMFormSet

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


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)

    # Update this exact line to match your model's related_name!
    boms = product.bom_items.all()

    # Calculate costs dynamically
    bom_data = []
    total_production_cost = 0

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

        # Check that both the product details AND the recipe are valid
        if form.is_valid() and formset.is_valid():
            product = form.save()
            # Attach the new product to the raw materials before saving
            formset.instance = product
            formset.save()
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
        product.delete()
        return redirect('inventory:product_list')
    return render(request, 'inventory/product_confirm_delete.html', {'item': product})

"""
@login_required
@user_passes_test(is_staff_check, login_url='/')
def bom_create(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        form = BOMForm(request.POST)
        if form.is_valid():
            bom = form.save(commit=False)
            bom.product = product
            bom.save()
            return redirect('inventory:product_detail', pk=product.id)
    else:
        form = BOMForm()

    return render(request, 'inventory/product_form.html', {
        'form': form,
        'title': f'Add Material to {product.name}'
    })"""