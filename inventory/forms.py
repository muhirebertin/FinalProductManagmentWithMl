# inventory/forms.py
from django import forms
from django.forms import inlineformset_factory
from .models import RawMaterial, Product, BillOfMaterial

# 1. The missing Raw Material form
class RawMaterialForm(forms.ModelForm):
    class Meta:
        model = RawMaterial
        fields = ['code', 'name', 'unit', 'quantity_in_stock', 'reorder_level', 'unit_cost']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Sq Meters'}),
            'quantity_in_stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control'}),
        }

# 2. The Product form
class ProductForm(forms.ModelForm):
    CATEGORY_CHOICES = [
        ('', 'Select a Category...'),
        ('Bags', 'Bags'),
        ('Belts', 'Belts'),
        ('Shoes', 'Shoes'),
        ('Folders', 'Folders'),
        ('Accessories', 'Accessories'),
    ]
    category = forms.ChoiceField(choices=CATEGORY_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}))

    class Meta:
        model = Product
        fields = ['code', 'name', 'category', 'unit_price']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., BAG-001'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control'}),
        }

# 3. The newly corrected BOM form
class BOMForm(forms.ModelForm):
    class Meta:
        model = BillOfMaterial
        fields = ['material', 'quantity_per_unit']
        widgets = {
            'material': forms.Select(attrs={'class': 'form-control'}),
            'quantity_per_unit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'placeholder': 'Amount needed per unit'}),
        }

BOMFormSet = inlineformset_factory(
    Product,
    BillOfMaterial,
    form=BOMForm,
    extra=3,  # Displays 3 empty rows by default to build the recipe
    can_delete=True
)