from django import forms
from django.core.exceptions import ValidationError

from django_csv_import import ImportSchema
from tests.models import Item


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ("sku", "quantity", "label")

    def clean_sku(self):
        sku = self.cleaned_data["sku"].upper()
        if not sku.startswith("DEMO-"):
            raise ValidationError("SKU must start with DEMO-.", code="sku_prefix")
        return sku


ITEM_COLUMNS = {"SKU": "sku", "Quantity": "quantity", "Name": "label"}
ITEM_SCHEMA = ImportSchema(ItemForm, ITEM_COLUMNS)
