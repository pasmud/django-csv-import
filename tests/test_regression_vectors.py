import json
from io import BytesIO
from pathlib import Path

import pytest
from django import forms
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from django_csv_import import ImportSchema, Limits, import_csv, preview_csv
from example.catalog.forms import PRODUCT_IMPORT
from tests.forms import ITEM_SCHEMA, ItemForm
from tests.models import Item, Placement


class NoteForm(ItemForm):
    class Meta(ItemForm.Meta):
        fields = (*ItemForm.Meta.fields, "internal_note")


class ActiveForm(ItemForm):
    active = forms.TypedChoiceField(
        choices=[("yes", "Yes"), ("no", "No")],
        coerce={"yes": True, "no": False}.__getitem__,
    )

    class Meta(ItemForm.Meta):
        fields = (*ItemForm.Meta.fields, "active")


class PlacementForm(forms.ModelForm):
    class Meta:
        model = Placement
        fields = ("slot",)


ITEM_FIELDS = ("sku", "quantity", "label", "internal_note", "active")
PROFILES = {
    "item": (ITEM_SCHEMA, ITEM_FIELDS),
    "note": (
        ImportSchema(NoteForm, {**ITEM_SCHEMA.columns, "Note": "internal_note"}),
        ITEM_FIELDS,
    ),
    "active": (
        ImportSchema(ActiveForm, {**ITEM_SCHEMA.columns, "Active": "active"}),
        ITEM_FIELDS,
    ),
    "placement": (ImportSchema(PlacementForm, {"Slot": "slot"}), ("item_id", "slot")),
    "product": (PRODUCT_IMPORT, ("sku", "price", "stock", "name")),
}
VECTORS = sorted(Path(__file__).with_name("regression_vectors").glob("*.json"))


@pytest.fixture
def isolated_database(sqlite_database):
    # Each case exercises the service's own transaction/savepoint, then clears its data.
    with transaction.atomic():
        yield
        transaction.set_rollback(True)


def assert_issues(issues, expected):
    # Django versions may emit field and model errors in different orders.
    issues = sorted(
        issues, key=lambda issue: (issue.line or 0, issue.column or "", issue.code)
    )
    expected = sorted(
        expected, key=lambda vector: (vector[0] or 0, vector[1] or "", vector[2])
    )
    triples = [(i.line, i.column, i.code) for i in issues]
    assert triples == [tuple(i[:3]) for i in expected]
    for issue, vector in zip(issues, expected, strict=True):
        if len(vector) == 4:
            assert issue.message == vector[3]


@pytest.mark.parametrize("path", VECTORS, ids=[path.stem for path in VECTORS])
def test_csv_regression_vector(path, request):
    case = json.loads(path.read_text(encoding="utf-8"))
    fixture = "database" if case.get("top_level_transaction") else "isolated_database"
    request.getfixturevalue(fixture)
    base, fields = PROFILES[case.get("profile", "item")]
    schema = ImportSchema(
        base.form_class,
        case.get("columns", base.columns),
        Limits(**case["limits"]) if "limits" in case else base.limits,
    )
    model = schema.model
    if model is Placement and case.get("parent", True):
        Item.objects.create(pk=1001, sku="DEMO-PARENT", quantity=1, label="Parent")
    for row in case.get("existing", []):
        model.objects.create(**row)

    def stored():
        return [
            [
                str(value) if name == "price" else value
                for name, value in zip(fields, row, strict=True)
            ]
            for row in model.objects.order_by("pk").values_list(*fields)
        ]

    raw = case["csv"].encode() if "csv" in case else bytes.fromhex(case["csv_hex"])
    expected = case["expect"]
    before = stored()
    preview = preview_csv(BytesIO(raw), schema)
    assert preview.ok is (not expected["issues"])
    assert preview.row_count == expected["row_count"]
    assert list(preview.headers) == expected["headers"]
    samples = [[record.line, *record.cells] for record in preview.sample]
    assert samples == expected["sample"]
    assert_issues(preview.issues, expected["issues"])
    assert stored() == before

    for row in case.get("before_apply", []):
        model.objects.create(**row)
    before = stored()
    with CaptureQueriesContext(connection) as queries:
        applied = import_csv(BytesIO(raw), schema)
    if "insert_attempts" in expected:
        prefix = f'INSERT INTO "{model._meta.db_table}"'
        attempts = sum(query["sql"].startswith(prefix) for query in queries)
        assert attempts == expected["insert_attempts"]
    apply_issues = expected.get("apply_issues", expected["issues"])
    assert applied.ok is (not apply_issues)
    assert applied.row_count == expected["row_count"]
    assert_issues(applied.issues, apply_issues)
    assert applied.created_count == len(expected["created"])
    assert stored() == before + expected["created"]
