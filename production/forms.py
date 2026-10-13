# production/forms.py
from django import forms
from .models import ProductionTask

class ProductionTaskForm(forms.ModelForm):
    class Meta:
        model = ProductionTask
        fields = ['title', 'description', 'assigned_to', 'status', 'due_date']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Cut 50 leather belts'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'assigned_to': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            # The 'date' type renders a calendar dropdown in the browser
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }