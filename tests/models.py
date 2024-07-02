from django.core.exceptions import ValidationError
from django.db import models


class Item(models.Model):
    sku = models.CharField(max_length=12, unique=True)
    quantity = models.PositiveIntegerField()
    label = models.CharField(max_length=40)
    internal_note = models.CharField(max_length=40, default="server default")
    active = models.BooleanField(default=True)

    def clean(self):
        if self.label.casefold() == "reserved":
            raise ValidationError("Choose a different name.", code="reserved_name")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("label", "quantity"), name="test_item_label_quantity"),
            models.CheckConstraint(
                condition=models.Q(quantity__lte=500),
                name="test_item_quantity_limit",
                violation_error_message="Quantity must not exceed 500.",
            ),
        ]
