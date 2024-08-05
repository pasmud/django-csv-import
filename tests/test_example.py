from decimal import Decimal
from pathlib import Path

import pytest

from django_csv_import import import_csv, preview_csv
from example.catalog.forms import PRODUCT_IMPORT
from example.catalog.models import Product

EXAMPLE = Path(__file__).resolve().parents[1] / "example"
pytestmark = pytest.mark.usefixtures("database")


def test_synthetic_example_imports_and_reports_errors_in_the_invalid_sample():
    with (EXAMPLE / "products-invalid.csv").open("rb") as upload:
        preview = preview_csv(upload, PRODUCT_IMPORT)
    assert [(i.line, i.column, i.code) for i in preview.issues] == [
        (3, "SKU", "duplicate_row"), (4, "Unit price", "invalid"), (5, "Stock", "min_value"),
    ]
    assert not Product.objects.exists()
    with (EXAMPLE / "products.csv").open("rb") as upload:
        result = import_csv(upload, PRODUCT_IMPORT)
    assert result.ok and result.created_count == 3
    item = Product.objects.get(sku="DEMO-MAP")
    assert (item.name, item.price, item.stock) == ("Trail map, pocket edition", Decimal("4.25"), 12)
    assert Product.objects.filter(sku="DEMO-CAFÉ").exists()
