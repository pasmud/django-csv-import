import pytest
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from django_csv_import import ImportSchema, Limits
from example.catalog.forms import PRODUCT_IMPORT
from tests.forms import ITEM_COLUMNS, ItemForm
from tests.models import Item

pytestmark = pytest.mark.usefixtures("database")
VALID = b"SKU,Quantity,Name\nDEMO-A,1,Map\n"


def staff_client(*permissions, enforce_csrf=False, **user_options):
    user = User.objects.create(username="demo-staff", is_staff=True, **user_options)
    user.user_permissions.set(Permission.objects.filter(
        content_type__app_label="tests", codename__in=permissions,
    ))
    client = Client(enforce_csrf_checks=enforce_csrf)
    client.force_login(user)
    return client


def post_csv(client, mode, raw=VALID, **headers):
    return client.post(reverse("admin:tests_item_import_csv"), {
        "mode": mode,
        "upload": SimpleUploadedFile("demo.csv", raw, content_type="text/csv"),
    }, **headers)


def test_changelist_link_requires_add_and_direct_post_is_forbidden_without_it():
    client = staff_client("view_item")
    url = reverse("admin:tests_item_import_csv")
    listing = client.get(reverse("admin:tests_item_changelist"))
    assert listing.status_code == 200 and url.encode() not in listing.content
    assert client.get(url).status_code == 403
    assert post_csv(client, "apply").status_code == 403
    assert not Item.objects.exists()


def test_admin_preview_is_csrf_protected_read_only_and_apply_revalidates():
    client = staff_client("add_item", "view_item", enforce_csrf=True)
    url = reverse("admin:tests_item_import_csv")
    assert url.encode() in client.get(reverse("admin:tests_item_changelist")).content
    assert client.get(url).status_code == 200
    assert post_csv(client, "preview").status_code == 403
    assert post_csv(client, "apply").status_code == 403
    headers = {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}
    preview = post_csv(client, "preview", **headers)
    assert preview.status_code == 200
    assert b"1 row passed validation" in preview.content
    assert b"Sample of valid input rows" in preview.content
    assert not Item.objects.exists()

    Item.objects.create(sku="DEMO-A", quantity=4, label="Existing")
    apply = post_csv(client, "apply", **headers)
    assert apply.status_code == 200
    assert b"Line 2, SKU:" in apply.content
    assert b"No rows saved" in apply.content
    assert Item.objects.count() == 1


def test_add_only_staff_can_import_and_redirects_to_accessible_page():
    client = staff_client("add_item")
    response = post_csv(client, "apply")
    assert response.status_code == 302
    assert response.url == reverse("admin:tests_item_import_csv")
    assert b"Imported 1 row." in client.get(response.url).content
    assert Item.objects.get().sku == "DEMO-A"


@pytest.mark.parametrize("account", [None, {"is_staff": False}, {"is_staff": True, "is_active": False}])
def test_admin_site_rejects_anonymous_nonstaff_and_inactive_accounts(account):
    client = Client()
    if account is not None:
        user = User.objects.create(username="demo-no-access", **account)
        user.user_permissions.add(Permission.objects.get(content_type__app_label="tests", codename="add_item"))
        client.force_login(user)
    response = post_csv(client, "apply")
    assert response.status_code == 302 and response.url.startswith(reverse("admin:login") + "?")
    assert not Item.objects.exists()


def test_admin_rejects_excess_bytes_and_rows_for_disk_backed_uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "FILE_UPLOAD_MAX_MEMORY_SIZE", 0)
    monkeypatch.setattr(settings, "FILE_UPLOAD_TEMP_DIR", str(tmp_path))
    schema = ImportSchema(ItemForm, ITEM_COLUMNS, Limits(max_bytes=64, max_rows=1))
    monkeypatch.setattr(admin.site.get_model_admin(Item), "csv_import_schema", schema)
    client = staff_client("add_item")
    excessive_bytes = post_csv(client, "apply", VALID + b"x" * 64)
    assert excessive_bytes.status_code == 200 and b"CSV exceeds 64 bytes." in excessive_bytes.content
    excessive_rows = post_csv(client, "apply", VALID + b"DEMO-B,2,Lamp\n")
    assert excessive_rows.status_code == 200 and b"Line 3: CSV exceeds the data row limit (1)." in excessive_rows.content
    assert not Item.objects.exists()


def test_preview_escapes_csv_text_and_rejects_unknown_action():
    client = staff_client("add_item")
    raw = b"SKU,Quantity,Name\nDEMO-A,1,Maps & notes < pocket >\n"
    preview = post_csv(client, "preview", raw)
    assert b"Maps &amp; notes &lt; pocket &gt;" in preview.content
    invalid = post_csv(client, "unknown", raw)
    assert invalid.status_code == 200 and b"Select a valid choice." in invalid.content
    assert not Item.objects.exists()


def test_admin_displays_cell_limit_and_rejects_apply_atomically(monkeypatch):
    schema = ImportSchema(ItemForm, ITEM_COLUMNS, Limits(max_cell_chars=8))
    monkeypatch.setattr(admin.site.get_model_admin(Item), "csv_import_schema", schema)
    client = staff_client("add_item")
    response = post_csv(client, "apply", VALID + b"DEMO-B,2,Long name\n")
    assert response.status_code == 200
    assert b"may contain up to 8 characters" in response.content
    assert b"Line 3: Cell 3 exceeds 8 characters." in response.content
    assert not Item.objects.exists()


def test_report_mode_is_disabled_by_default():
    client = staff_client("add_item")
    url = reverse("admin:tests_item_import_csv")
    assert b"Download validation report" not in client.get(url).content
    response = post_csv(client, "report")
    assert response.status_code == 200 and b"Select a valid choice." in response.content
    assert not Item.objects.exists()


def test_enabled_report_checks_csrf_and_omits_sample_and_validation_messages(monkeypatch):
    class ReportForm(ItemForm):
        def clean_label(self):
            label = self.cleaned_data["label"]
            if label.startswith("Private"):
                raise ValidationError(f"Unknown label: {label}", code="unknown_label")
            return label

    model_admin = admin.site.get_model_admin(Item)
    monkeypatch.setattr(model_admin, "csv_import_report_enabled", True)
    monkeypatch.setattr(model_admin, "csv_import_schema", ImportSchema(ReportForm, ITEM_COLUMNS))
    client = staff_client("add_item", enforce_csrf=True)
    url = reverse("admin:tests_item_import_csv")
    assert b"Download validation report" in client.get(url).content
    raw = VALID + b"DEMO-B,2,Private description\n"
    assert post_csv(client, "report", raw).status_code == 403
    response = post_csv(client, "report", raw, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert response.status_code == 200
    assert response.headers["Content-Disposition"] == 'attachment; filename="csv-validation-report.json"'
    assert "no-store" in response.headers["Cache-Control"]
    assert response.json() == {
        "ok": False, "row_count": 2,
        "issues": [{"line": 3, "column": "Name", "code": "unknown_label"}],
    }
    assert b"Private description" not in response.content and b"DEMO-A" not in response.content
    assert not Item.objects.exists()


def test_report_requires_model_add_permission_even_when_enabled(monkeypatch):
    monkeypatch.setattr(admin.site.get_model_admin(Item), "csv_import_report_enabled", True)
    assert post_csv(staff_client("view_item"), "report").status_code == 403


def test_request_schema_controls_headers_and_import_availability(monkeypatch):
    model_admin = admin.site.get_model_admin(Item)
    schema = ImportSchema(ItemForm, {"Code": "sku", "Count": "quantity", "Label": "label"})

    def schema_for(request):
        return schema if request.user.has_perm("tests.change_item") else None

    monkeypatch.setattr(model_admin, "get_csv_import_schema", schema_for)
    client = staff_client("add_item", "view_item", "change_item")
    url = reverse("admin:tests_item_import_csv")
    list_url = reverse("admin:tests_item_changelist")
    assert url.encode() in client.get(list_url).content
    assert b"<code>Code</code>" in client.get(url).content
    assert b"Required header is absent." in post_csv(client, "apply").content
    raw = b"Code,Count,Label\nDEMO-A,1,Map\n"
    assert b"1 row passed validation" in post_csv(client, "preview", raw).content
    assert not Item.objects.exists()
    assert post_csv(client, "apply", raw).url == list_url
    assert Item.objects.get().internal_note == "server default"

    User.objects.get(username="demo-staff").user_permissions.remove(
        Permission.objects.get(content_type__app_label="tests", codename="change_item"),
    )
    assert url.encode() not in client.get(list_url).content
    assert client.get(url).status_code == 404
    assert post_csv(client, "apply", raw.replace(b"DEMO-A", b"DEMO-B")).status_code == 404
    assert Item.objects.count() == 1


def test_add_permission_is_checked_before_selecting_a_request_schema(monkeypatch):
    def unexpected_hook(request):
        pytest.fail("Schema selection ran without add permission")

    monkeypatch.setattr(admin.site.get_model_admin(Item), "get_csv_import_schema", unexpected_hook)
    client = staff_client("view_item")
    assert client.get(reverse("admin:tests_item_changelist")).status_code == 200
    assert post_csv(client, "apply").status_code == 403


def test_request_schema_cannot_target_another_model(monkeypatch):
    monkeypatch.setattr(admin.site.get_model_admin(Item), "get_csv_import_schema", lambda request: PRODUCT_IMPORT)
    with pytest.raises(ImproperlyConfigured, match="this ModelAdmin's model"):
        post_csv(staff_client("add_item"), "apply")
