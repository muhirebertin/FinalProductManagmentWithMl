# production/forms.py
from django import forms
from .models import ProductionTask
from employees.models import Employee

class ProductionTaskForm(forms.ModelForm):
    class Meta:
        model = ProductionTask
        fields = ['title', 'product', 'target_quantity', 'produced_quantity', 'assigned_to', 'status', 'due_date', 'description']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'product': forms.Select(attrs={'class': 'form-control'}),
            'target_quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'produced_quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'assigned_to': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = Employee.objects.filter(is_active=True)