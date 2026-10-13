# inventory/models.py
from django.db import models
from django.core.validators import MinValueValidator


class RawMaterial(models.Model):
    code = models.CharField(max_length=20, unique=True, help_text="e.g., RM-001")
    name = models.CharField(max_length=100, help_text="e.g., Full Grain Leather")
    unit = models.CharField(max_length=20, help_text="e.g., Sq Meters, Pieces, Spools")
    quantity_in_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                            validators=[MinValueValidator(0)])
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=0, help_text="Cost in RWF")

    def __str__(self):
        return f"{self.code} - {self.name}"


class Product(models.Model):
    code = models.CharField(max_length=20, unique=True, help_text="e.g., LM-BAG-01")
    name = models.CharField(max_length=100, help_text="e.g., Handcrafted Leather Tote")
    category = models.CharField(max_length=50)
    unit_price = models.DecimalField(max_digits=10, decimal_places=0, help_text="Selling price in RWF")

    # The ManyToMany relationship through BillOfMaterial
    materials = models.ManyToManyField(RawMaterial, through='BillOfMaterial', related_name='products')

    def __str__(self):
        return f"{self.code} - {self.name}"


class BillOfMaterial(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='bom_items')
    material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT)
    quantity_per_unit = models.DecimalField(max_digits=10, decimal_places=4, validators=[MinValueValidator(0.0001)])

    class Meta:
        # Business rule: The same material cannot be added twice to one product
        constraints = [
            models.UniqueConstraint(fields=['product', 'material'], name='unique_bom_material')
        ]

    def __str__(self):
        return f"{self.quantity_per_unit} {self.material.unit} of {self.material.name} for {self.product.name}"