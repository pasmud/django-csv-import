from django.core.validators import MinValueValidator
from django.db import models


class Product(models.Model):
    sku = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    stock = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(price__gte=0), name="product_nonnegative_price")]
        ordering = ("sku",)

    def __str__(self):
        return f"{self.sku}: {self.name}"
