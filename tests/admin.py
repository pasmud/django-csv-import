from django.contrib import admin

from django_csv_import.admin import CSVImportAdminMixin
from tests.forms import ITEM_SCHEMA
from tests.models import Item


@admin.register(Item)
class ItemAdmin(CSVImportAdminMixin, admin.ModelAdmin):
    csv_import_schema = ITEM_SCHEMA
