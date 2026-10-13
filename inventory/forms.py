# inventory/forms.py
from django import forms
from .models import RawMaterial

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