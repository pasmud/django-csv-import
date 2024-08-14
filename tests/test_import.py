from io import BytesIO

import pytest
from django import forms
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from django_csv_import import ImportSchema, import_csv, preview_csv
from tests.forms import ITEM_SCHEMA
from tests.models import Item, Placement

pytestmark = pytest.mark.usefixtures("database")
HEADER = b"SKU,Quantity,Name\n"


def test_apply_inserts_validated_rows_and_preserves_unmapped_defaults():
    raw = HEADER + b"demo-a,1,Map\nDEMO-B,2,Lantern\n"
    result = import_csv(BytesIO(raw), ITEM_SCHEMA)
    assert result.ok and result.row_count == result.created_count == 2
    assert list(Item.objects.order_by("sku").values_list("sku", "quantity", "internal_note")) == [
        ("DEMO-A", 1, "server default"), ("DEMO-B", 2, "server default"),
    ]


def test_apply_checks_current_state_even_after_a_clean_preview():
    raw = HEADER + b"DEMO-A,1,Map\nDEMO-B,2,Lantern\n"
    assert preview_csv(BytesIO(raw), ITEM_SCHEMA).ok
    Item.objects.create(sku="DEMO-B", quantity=5, label="Existing")
    result = import_csv(BytesIO(raw), ITEM_SCHEMA)
    assert not result.ok and result.created_count == 0
    assert [(i.line, i.column, i.code) for i in result.issues] == [(3, "SKU", "unique")]
    assert list(Item.objects.values_list("sku", flat=True)) == ["DEMO-B"]


def test_database_failure_after_an_insert_rolls_back_the_import_and_leaves_outer_transaction_usable():
    raw = HEADER + b"DEMO-A,1,Map\nDEMO-B,2,Archive\n"
    assert preview_csv(BytesIO(raw), ITEM_SCHEMA).ok
    with transaction.atomic():
        Item.objects.create(sku="DEMO-OLD", quantity=3, label="Existing")
        with CaptureQueriesContext(connection) as queries:
            result = import_csv(BytesIO(raw), ITEM_SCHEMA)
        assert sum(query["sql"].startswith('INSERT INTO "tests_item"') for query in queries) == 2
        assert not result.ok and result.row_count == 2 and result.created_count == 0
        issue, = result.issues
        assert (issue.line, issue.column, issue.code) == (3, None, "integrity")
        assert "test_archive_requires_note" not in issue.message
        assert list(Item.objects.values_list("sku", flat=True)) == ["DEMO-OLD"]
    assert Item.objects.count() == 1


def test_deferred_database_failure_rolls_back_at_commit_without_claiming_a_row_number():
    class PlacementForm(forms.ModelForm):
        class Meta:
            model = Placement
            fields = ("slot",)

    schema = ImportSchema(PlacementForm, {"Slot": "slot"})
    raw = b'Slot\n1\n""\n'
    assert preview_csv(BytesIO(raw), schema).ok
    result = import_csv(BytesIO(raw), schema)
    assert not result.ok and result.row_count == 2 and result.created_count == 0
    issue, = result.issues
    assert (issue.code, issue.line, issue.column) == ("integrity", None, None)
    assert not Placement.objects.exists()

    Item.objects.create(pk=1001, sku="DEMO-PARENT", quantity=1, label="Existing")
    assert import_csv(BytesIO(raw), schema).created_count == 2
    assert set(Placement.objects.values_list("slot", flat=True)) == {1, None}
