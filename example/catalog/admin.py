from django.contrib import admin

from django_csv_import.admin import CSVImportAdminMixin

from .forms import PRODUCT_IMPORT
from .models import Product


@admin.register(Product)
class ProductAdmin(CSVImportAdminMixin, admin.ModelAdmin):
    csv_import_schema = PRODUCT_IMPORT
    list_display = ("sku", "name", "price", "stock", "created_at")
    search_fields = ("sku", "name")
