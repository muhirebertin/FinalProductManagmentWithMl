# analytics/forms.py
import datetime as dt

from django import forms
from django.utils import timezone

from employees.models import Employee
from inventory.models import Product

from .models import IncomingOrder


class PredictionForm(forms.Form):
    """What-if simulation: 'What happens if we produce X units of P by date D?'"""
    product = forms.ModelChoiceField(queryset=Product.objects.order_by("category", "name"),
                                     widget=forms.Select(attrs={"class": "form-control"}))
    quantity = forms.IntegerField(min_value=1, max_value=10000, initial=10,
                                  widget=forms.NumberInput(attrs={"class": "form-control"}))
    due_date = forms.DateField(widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))
    artisan = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True).select_related("department"),
        required=False, empty_label="Let the AI recommend the best artisan",
        widget=forms.Select(attrs={"class": "form-control"}))
    customer = forms.CharField(max_length=120, required=False,
                               widget=forms.TextInput(attrs={"class": "form-control",
                                                             "placeholder": "Optional - used if you submit it as an order"}))
    channel = forms.ChoiceField(choices=IncomingOrder.CHANNEL_CHOICES, initial="Internal",
                                widget=forms.Select(attrs={"class": "form-control"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["due_date"].initial = timezone.localdate() + dt.timedelta(days=14)

    def clean_due_date(self):
        due = self.cleaned_data["due_date"]
        if due <= timezone.localdate():
            raise forms.ValidationError("The due date must be in the future.")
        if due > timezone.localdate() + dt.timedelta(days=730):
            raise forms.ValidationError("Please choose a due date within the next two years.")
        return due


class APIKeyForm(forms.Form):
    name = forms.CharField(max_length=80, initial="Production terminal",
                           widget=forms.TextInput(attrs={"class": "form-control",
                                                         "placeholder": "e.g. Simulator, MES terminal 1"}))
