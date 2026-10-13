# employees/models.py
from django.db import models

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class Employee(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    # The ForeignKey satisfies the first database relationship requirement
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='employees')
    hire_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Contract(models.Model):
    CONTRACT_TYPES = [
        ('Permanent', 'Permanent'),
        ('Temporary', 'Temporary'),
        ('Intern', 'Intern'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='contracts')
    contract_type = models.CharField(max_length=20, choices=CONTRACT_TYPES)
    start_date = models.DateField()
    # end_date can be blank for Permanent contracts
    end_date = models.DateField(blank=True, null=True)
    # Using decimal places=0 for standard RWF formatting
    base_salary = models.DecimalField(max_digits=10, decimal_places=0, help_text="Monthly Salary in RWF")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.employee} - {self.contract_type} Contract"


class LeaveRequest(models.Model):
    LEAVE_TYPES = [
        ('Annual', 'Annual Leave'),
        ('Sick', 'Sick Leave'),
        ('Maternity', 'Maternity Leave'),
        ('Unpaid', 'Unpaid Leave'),
    ]
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    applied_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee} ({self.get_leave_type_display()})"