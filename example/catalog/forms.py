from django import forms
from django.core.exceptions import ValidationError

from django_csv_import import ImportSchema, Limits

from .models import Product


class ProductImportForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ("sku", "name", "price", "stock")

    def clean_sku(self):
        sku = self.cleaned_data["sku"].upper()
        if not sku.startswith("DEMO-"):
            raise ValidationError("Use a synthetic SKU starting with DEMO-.", code="demo_sku")
        return sku


PRODUCT_IMPORT = ImportSchema(
    ProductImportForm,
    {"SKU": "sku", "Product name": "name", "Unit price": "price", "Stock": "stock"},
    Limits(max_bytes=128 * 1024, max_rows=250),
)
