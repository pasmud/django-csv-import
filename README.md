# django-csv-import

Add CSV imports to a Django model or its admin. Explicit column allowlists and Django validation produce line-level feedback; successful imports insert all rows in a single transaction. There are no runtime dependencies beyond Django.

All sample data is synthetic.

## Install and try the example

Requires Python 3.11+ with Django 5.2 LTS, or Python 3.12+ with Django 6.0. From a checkout in an activated virtual environment:

```sh
python -m pip install .
python -m django migrate --settings=example.settings
python -m django createsuperuser --settings=example.settings
python -m django runserver 127.0.0.1:8000 --settings=example.settings
```

Use a throwaway account for this local-only project. Sign in at `http://127.0.0.1:8000/admin/` and open **Products → Import CSV**. Preview [`example/products.csv`](example/products.csv), then select it again and click **Import rows**. On a fresh database, [`example/products-invalid.csv`](example/products-invalid.csv) illustrates an in-file duplicate, an invalid price, and negative stock. The SQLite database is local to `example/`; the demo's generated secret resets sessions when the process restarts.

## Integrate with a Django model

Add `"django_csv_import"` to `INSTALLED_APPS` for the admin templates. Use your existing Django admin, middleware, and app-directory template loading. Define an import-specific `ModelForm` and map each CSV header to one of its fields:

```python
from django import forms
from django.contrib import admin

from django_csv_import import ImportSchema, Limits
from django_csv_import.admin import CSVImportAdminMixin

from .models import Product


class ProductImportForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ("sku", "name", "price", "stock")


product_schema = ImportSchema(
    ProductImportForm,
    {"SKU": "sku", "Product name": "name", "Unit price": "price", "Stock": "stock"},
    Limits(max_bytes=128 * 1024, max_rows=250),
)


@admin.register(Product)
class ProductAdmin(CSVImportAdminMixin, admin.ModelAdmin):
    csv_import_schema = product_schema
```

The mixin uses the admin site's active-staff gate and CSRF protection, then enforces the model admin's `has_add_permission(request)` for both preview and apply. The link appears on the changelist for users who can add. Add-only staff can open the import URL directly (`import-csv/` under the model's admin URL); they do not gain changelist access. If you override `change_list_template`, extend `django_csv_import/change_list.html` or render the `csv_import_url` context value when present.

Override `get_csv_import_schema(self, request)` to select among trusted schemas for the registered model, for example to support a team's CSV headers or apply narrower limits. The default returns `csv_import_schema`. Return `None` to hide the link and make the import view unavailable for that request. The admin checks add permission before calling the hook, and selects the schema again on each upload.

Set `csv_import_report_enabled = True` on the model admin to offer a **Download validation report (JSON)** button. It validates the selected upload without writing, under the same add-permission and CSRF checks as preview. The attachment contains `ok`, `row_count`, and all issue codes with their line and column when available. It omits validation messages and sampled cell values. Use static codes for custom Django validators. Upload form errors (such as a missing or oversized file) still appear on the page.

### CSV and validation contract

- Pass UTF-8 with an optional BOM, comma delimiters and standard double-quote escaping. Quoted commas and multiline values are supported. Physically empty lines are ignored; quoted empty fields still count. NUL characters are rejected. Python's CSV parser also enforces its per-field size limit.
- The first nonblank record is the header. Names are exact and case-sensitive, with no implicit trimming. Every mapped column must appear once, in any order, with no extra columns. Empty or whitespace-only header cells report `blank_header`; repeated configured headers identify the column, while unexpected names are not echoed in diagnostics. Each data record must match the header width; a header-only file is rejected.
- Defaults are 1 MiB and 1,000 data records. `Limits` may lower or raise either bound. Set `max_cell_chars` to a positive integer to also cap decoded characters in each header or data cell after CSV unquoting. An oversized cell reports `cell_too_long` with the record's start line and the 1-based cell position in the message. The default `None` leaves Python's CSV parser limit in effect; setting a cap does not raise that parser limit. These are per-file parsing limits; configure an HTTP request body limit separately for multipart traffic.
- The mapping must cover the explicit model form fields one-to-one. Mapped fields must be editable scalar fields: no primary keys, relations, generated fields, files, disabled fields or widgets that need multiple inputs. For Boolean inputs use a `TypedChoiceField` with explicit text choices instead of the standard checkbox. Unmapped fields take server-side defaults or can be set by trusted model logic.
- Django performs field, form, and model validation as it would for the configured `ModelForm`. Call `super().clean()` if you override its `clean()`. Django can skip field-dependent checks on omitted fields. The importer also detects in-file repeats of exact cleaned values for mapped `unique` fields, `unique_together`, and plain unconditional field-based `UniqueConstraint`s. Database collation, conditional or expression constraints, and concurrent changes can still cause an apply to fail.

## Python API

Use `preview_csv(source, schema)` and `import_csv(source, schema)` with a binary stream positioned at the start of the CSV. The caller owns the stream and, outside admin, is responsible for access control.

```python
from django_csv_import import import_csv, preview_csv

with open("example/products.csv", "rb") as upload:
    preview = preview_csv(upload, product_schema)

if preview.ok:
    # After reviewing the preview, reopen the file for a new validation pass.
    with open("example/products.csv", "rb") as upload:
        result = import_csv(upload, product_schema)
    print(result.created_count, result.issues)
else:
    for issue in preview.issues:
        print(issue.line, issue.column, issue.code, issue.message)
```

Both return `ok`, `row_count` (data records found; zero if parsing aborts), and `issues` (a tuple of `Issue`). Each issue carries `code`, `message`, and optional `line` (1-based physical start line) and `column` (the CSV header, when applicable). Structural codes include `too_large`, `too_many_rows`, `missing_header`, and `row_width`; validation codes generally come from Django. `Preview` also returns `headers` and `sample` (up to ten valid raw records with `line` and `cells`). `ImportResult` adds `created_count`, which is zero on failure. Admin displays up to 100 issues and shortens preview cell text.

Preview does not write, lock, or reserve records. Apply accepts a fresh upload and revalidates it; no server-side preview token or saved upload is used. Apply is create-only: no upserts or partial success. A database integrity failure rolls back the batch and returns a generic `integrity` issue with a line when known. Other database or application exceptions propagate after rollback. Django's model `save()` and signals run on apply; the importer saves the validated form instance directly rather than calling the form's `save()` override. Keep validation read-only and defer external side effects with `transaction.on_commit()` as appropriate. Atomicity covers the model's routed write database only; use consistent read/write routing for validation. If called inside an outer transaction, final commit and any deferred checks belong to that outer transaction.

## Develop and verify

```sh
python -m pip install '.[dev]'
python -m pytest -q
ruff check .
python -m build
python -m twine check --strict dist/*
```

Tests use real Django and temporary SQLite databases. CI checks the supported Django branches on multiple Python versions and smoke-tests the installed wheel. See [LICENSE](LICENSE) for MIT terms.
