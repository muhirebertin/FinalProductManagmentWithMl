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

    @property
    def progress_percentage(self):
        if self.target_quantity == 0:
            return 0
        # Calculates the percentage and rounds it to a whole number
        return int((self.produced_quantity / self.target_quantity) * 100)

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

        # 2. Smart State & Quantitative Validation
        if self.produced_quantity > self.target_quantity:
            raise ValidationError({'produced_quantity': 'Produced quantity cannot exceed the target quantity.'})

        # Rule A: Pending tasks must have 0 progress
        if self.status == 'Pending' and self.produced_quantity > 0:
            raise ValidationError({
                'status': 'A task with production progress must be marked as "In Progress".',
                'produced_quantity': 'Progress must be 0 for a Pending task.'
            })

        # Rule B: Completed tasks must be at 100% progress
        if self.status == 'Completed' and self.produced_quantity != self.target_quantity:
            raise ValidationError({
                'status': f'Cannot mark as Completed. You have only produced {self.produced_quantity} out of {self.target_quantity}.',
                'produced_quantity': 'Must equal the target quantity to complete the task.'
            })

        # Rule C: If a task reaches 100%, force the user to mark it Completed
        if self.status == 'In Progress' and self.produced_quantity == self.target_quantity:
            raise ValidationError({
                'status': 'Target quantity reached! Please change the status to "Completed".'
            })


        if not self.pk and self.product and self.target_quantity:
            for bom in self.product.bom_items.all():
                required_qty = bom.quantity_per_unit * self.target_quantity
                if required_qty > bom.material.quantity_in_stock:
                    raise ValidationError({
                        'target_quantity': f'Not enough {bom.material.name} in stock! Need {required_qty} {bom.material.unit}, but only have {bom.material.quantity_in_stock}.'
                    })

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_target = self.target_quantity if self.pk else 0

    def clean(self):
        # 1. State machine Rules
        if self.produced_quantity > self.target_quantity:
            raise ValidationError({'produced_quantity': 'Produced quantity cannot exceed the target quantity.'})
        if self.status == 'Pending' and self.produced_quantity > 0:
            raise ValidationError({'status': 'A task with production progress must be marked as "In Progress".'})
        if self.status == 'Completed' and self.produced_quantity != self.target_quantity:
            raise ValidationError(
                {'status': f'Cannot complete. Produced {self.produced_quantity} out of {self.target_quantity}.'})
        if self.status == 'In Progress' and self.produced_quantity == self.target_quantity:
            raise ValidationError({'status': 'Target quantity reached! Please change the status to "Completed".'})

        if self.product:
            new_target_added = self.target_quantity - self._original_target
            if new_target_added > 0:
                for bom in self.product.bom_items.all():
                    materials_needed = bom.quantity_per_unit * new_target_added
                    if materials_needed > bom.material.quantity_in_stock:
                        raise ValidationError({
                            'target_quantity': f"Insufficient stock for {bom.material.name}! Need {materials_needed} {bom.material.unit}, but only have {bom.material.quantity_in_stock}."
                        })

    def save(self, *args, **kwargs):
        new_target_added = self.target_quantity - self._original_target

        super().save(*args, **kwargs)
        if new_target_added != 0 and self.product:
            for bom in self.product.bom_items.all():
                consumed = bom.quantity_per_unit * new_target_added
                bom.material.quantity_in_stock -= consumed
                bom.material.save()

        self._original_target = self.target_quantity

    def delete(self, *args, **kwargs):
        if self.product:
            for bom in self.product.bom_items.all():
                refund = bom.quantity_per_unit * self.target_quantity
                bom.material.quantity_in_stock += refund
                bom.material.save()
        super().delete(*args, **kwargs)