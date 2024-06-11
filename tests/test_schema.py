import pytest
from django import forms
from django.core.exceptions import ImproperlyConfigured

from django_csv_import import ImportSchema
from django_csv_import.csv_input import Record
from tests.models import Item


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ("sku", "quantity", "label")


def test_column_mapping_is_copied_and_headers_may_be_reordered():
    columns = {"SKU": "sku", "Quantity": "quantity", "Name": "label"}
    schema = ImportSchema(ItemForm, columns)
    columns["Note"] = "internal_note"
    assert schema.model is Item
    assert schema._header_issues(Record(1, ("Name", "SKU", "Quantity"))) == ()
    assert "Note" not in schema.columns


def test_missing_unknown_and_duplicate_headers_are_reported_without_using_upload_values():
    schema = ImportSchema(ItemForm, {"SKU": "sku", "Quantity": "quantity", "Name": "label"})
    issues = schema._header_issues(Record(2, ("SKU", "SKU", "internal_note", "Quantity")))
    assert {(i.code, i.line, i.column) for i in issues} == {
        ("duplicate_header", 2, None), ("unknown_header", 2, None), ("missing_header", 2, "Name"),
    }


@pytest.mark.parametrize(
    "columns",
    [
        {"SKU": "sku"},
        {"SKU": "sku", "Quantity": "quantity", "Name": "label", "Extra": "sku"},
        {"SKU": "sku", "Quantity": "quantity", "Name": "internal_note"},
        {"": "sku", "Quantity": "quantity", "Name": "label"},
    ],
)
def test_form_and_mapping_must_agree_exactly(columns):
    with pytest.raises(ImproperlyConfigured):
        ImportSchema(ItemForm, columns)


def test_all_fields_opt_in_and_ambiguous_checkbox_are_refused():
    class AllFields(forms.ModelForm):
        class Meta:
            model = Item
            fields = "__all__"

    class Checkbox(forms.ModelForm):
        class Meta:
            model = Item
            fields = ("active",)

    with pytest.raises(ImproperlyConfigured, match="Meta.fields"):
        ImportSchema(AllFields, {"Active": "active"})
    with pytest.raises(ImproperlyConfigured, match="text widget"):
        ImportSchema(Checkbox, {"Active": "active"})
