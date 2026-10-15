# production/models.py
from django.db import models
from django.core.exceptions import ValidationError
import datetime
from employees.models import Employee, LeaveRequest
from inventory.models import Product


class ProductionTask(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
    ]

    title = models.CharField(max_length=200, help_text="e.g. Batch 1: Classic Belts")
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

    @property
    def is_overdue(self):
        if self.due_date and self.status != 'Completed':
            return self.due_date < datetime.date.today()
        return False

    @property
    def progress_percentage(self):
        if self.target_quantity == 0:
            return 0
        return int((self.produced_quantity / self.target_quantity) * 100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Track the original quantity when the object is loaded from the database
        self._original_target = self.target_quantity if self.pk else 0

    def clean(self):
        super().clean()
        today = datetime.date.today()

        # ----------------------------------------------------
        # 1. HR & DATE VALIDATION (Cross-field rules)[cite: 4]
        # ----------------------------------------------------
        if self.due_date:
            if self.due_date < today and self.status != 'Completed':
                raise ValidationError({'due_date': 'The due date cannot be in the past.'})

        if self.assigned_to:
            if not self.assigned_to.is_active:
                raise ValidationError({'assigned_to': 'Cannot assign tasks to an inactive artisan.'})

            if self.due_date:
                is_on_leave = LeaveRequest.objects.filter(
                    employee=self.assigned_to,
                    status='Approved',
                    start_date__lte=self.due_date,
                    end_date__gte=today
                ).exists()
                if is_on_leave:
                    raise ValidationError({
                        'assigned_to': 'Cannot assign task: This artisan has an approved leave overlapping this production period.'
                    })

        # ----------------------------------------------------
        # 2. STATE MACHINE VALIDATION[cite: 4]
        # ----------------------------------------------------
        if self.produced_quantity > self.target_quantity:
            raise ValidationError({'produced_quantity': 'Produced quantity cannot exceed the target quantity.'})

        if self.status == 'Pending' and self.produced_quantity > 0:
            raise ValidationError({
                'status': 'A task with production progress must be marked as "In Progress".',
                'produced_quantity': 'Progress must be 0 for a Pending task.'
            })

        if self.status == 'Completed' and self.produced_quantity != self.target_quantity:
            raise ValidationError({
                'status': f'Cannot mark as Completed. You have only produced {self.produced_quantity} out of {self.target_quantity}.',
                'produced_quantity': 'Must equal the target quantity to complete the task.'
            })

        if self.status == 'In Progress' and self.produced_quantity == self.target_quantity:
            raise ValidationError({
                'status': 'Target quantity reached! Please change the status to "Completed".'
            })

        # ----------------------------------------------------
        # 3. INVENTORY & BOM VALIDATION (Business rule)[cite: 4]
        # ----------------------------------------------------
        if self.product:
            # Check how much *extra* stock is needed compared to before
            new_target_added = self.target_quantity - self._original_target
            if new_target_added > 0:
                for bom in self.product.bom_items.all():
                    materials_needed = bom.quantity_per_unit * new_target_added
                    if materials_needed > bom.material.quantity_in_stock:
                        raise ValidationError({
                            'target_quantity': f"Insufficient stock for {bom.material.name}! Need {materials_needed} {bom.material.unit}, but only have {bom.material.quantity_in_stock}."
                        })

    def save(self, *args, **kwargs):
        # Calculate the delta (positive if increasing target, negative if decreasing)
        new_target_added = self.target_quantity - self._original_target

        super().save(*args, **kwargs)

        # Deduct or refund stock based on the delta
        if new_target_added != 0 and self.product:
            for bom in self.product.bom_items.all():
                consumed = bom.quantity_per_unit * new_target_added
                bom.material.quantity_in_stock -= consumed
                bom.material.save()

        # Update the tracker for the next time this instance is edited
        self._original_target = self.target_quantity

    def delete(self, *args, **kwargs):
        # Refund all materials back to the warehouse if the task is deleted
        if self.product:
            for bom in self.product.bom_items.all():
                refund = bom.quantity_per_unit * self.target_quantity
                bom.material.quantity_in_stock += refund
                bom.material.save()
        super().delete(*args, **kwargs)