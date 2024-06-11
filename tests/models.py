from django.db import models


class Item(models.Model):
    sku = models.CharField(max_length=12, unique=True)
    quantity = models.PositiveIntegerField()
    label = models.CharField(max_length=40)
    internal_note = models.CharField(max_length=40, default="server default")
    active = models.BooleanField(default=True)
