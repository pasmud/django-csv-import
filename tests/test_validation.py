from io import BytesIO

import pytest

from django_csv_import.validation import validate
from tests.forms import ITEM_SCHEMA
from tests.models import Item

pytestmark = pytest.mark.usefixtures("database")


def test_row_errors_from_shape_form_model_and_database_are_actionable():
    Item.objects.create(sku="DEMO-OLD", quantity=2, label="Existing")
    source = BytesIO(
        b"Name,Quantity,SKU\n"
        b'"Trail\nMap",3,demo-good\n'
        b"Missing,4\n"
        b"Bad quantity,three,other\n"
        b"Reserved,3,DEMO-NAME\n"
        b"Over limit,501,DEMO-LIMIT\n"
        b"Duplicate,3,demo-old\n"
    )
    result = validate(source, ITEM_SCHEMA)
    assert result.row_count == 6
    assert {(i.line, i.column, i.code) for i in result.issues} == {
        (4, None, "row_width"),
        (5, "Quantity", "invalid"),
        (5, "SKU", "sku_prefix"),
        (6, None, "reserved_name"),
        (7, None, "invalid"),
        (8, "SKU", "unique"),
    }
    assert any(i.message == "Quantity must not exceed 500." for i in result.issues)
    valid, = result.rows
    assert valid.record.line == 2
    assert valid.form.cleaned_data == {"label": "Trail\nMap", "quantity": 3, "sku": "DEMO-GOOD"}
    assert Item.objects.count() == 1


def test_unlisted_headers_are_refused_before_any_row_can_bind():
    result = validate(BytesIO(b"SKU,Quantity,Name,internal_note\nDEMO-A,1,Map,new\n"), ITEM_SCHEMA)
    assert not result.rows
    assert [issue.code for issue in result.issues] == ["unknown_header"]
