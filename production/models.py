# production/models.py
from django.db import models
from django.core.exceptions import ValidationError
import datetime
from employees.models import Employee, LeaveRequest
from inventory.models import Product  # Import the Product model


class ProductionTask(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
    ]

    title = models.CharField(max_length=200, help_text="e.g. Batch 1: Classic Belts")
    # Link the task to the exact product being made
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='tasks', null=True)
    target_quantity = models.PositiveIntegerField(default=1)
    produced_quantity = models.PositiveIntegerField(default=0)

    description = models.TextField(blank=True, null=True)
    assigned_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, related_name='tasks')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    due_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.produced_quantity}/{self.target_quantity})"

    # Dynamic property to instantly check if a task is overdue
    @property
    def is_overdue(self):
        if self.due_date and self.status != 'Completed':
            return self.due_date < datetime.date.today()
        return False

    def clean(self):
        super().clean()
        today = datetime.date.today()

        # 1. Existing Rule: Due date & Leave check
        if self.due_date:
            if self.due_date < today and self.status != 'Completed':
                raise ValidationError({'due_date': 'The due date cannot be in the past.'})

        if self.assigned_to and self.due_date:
            is_on_leave = LeaveRequest.objects.filter(
                employee=self.assigned_to,
                status='Approved',
                start_date__lte=self.due_date,
                end_date__gte=today
            ).exists()
            if is_on_leave:
                raise ValidationError({
                                          'assigned_to': 'Cannot assign task: This artisan has an approved leave during this production period.'})

        if self.assigned_to and not self.assigned_to.is_active:
            raise ValidationError({'assigned_to': 'Cannot assign tasks to an inactive artisan.'})

        # 2. New Quantitative Rules
        if self.produced_quantity > self.target_quantity:
            raise ValidationError({'produced_quantity': 'Produced quantity cannot exceed the target quantity.'})

        if self.status == 'Completed' and self.produced_quantity < self.target_quantity:
            raise ValidationError({'status': 'A task can only be marked Completed when all units are produced.'})

        # 3. The Bill of Materials (BOM) Stock Check
        # We only check this for NEW tasks (not self.pk) so we don't block saving updates later
        if not self.pk and self.product and self.target_quantity:
            for bom in self.product.bom_items.all():
                required_qty = bom.quantity_per_unit * self.target_quantity
                if required_qty > bom.material.quantity_in_stock:
                    raise ValidationError({
                        'target_quantity': f'Not enough {bom.material.name} in stock! Need {required_qty} {bom.material.unit}, but only have {bom.material.quantity_in_stock}.'
                    })