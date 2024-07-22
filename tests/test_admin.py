import pytest
from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

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
