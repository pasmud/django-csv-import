from io import BytesIO

import pytest

from django_csv_import import preview_csv
from tests.forms import ITEM_SCHEMA
from tests.models import Item

pytestmark = pytest.mark.usefixtures("database")


def test_preview_checks_normalized_and_composite_duplicates_without_writes():
    result = preview_csv(BytesIO(
        b"SKU,Quantity,Name\n"
        b"demo-a,1,Map\n"
        b"DEMO-A,2,Lantern\n"
        b"DEMO-B,01,Map\n"
    ), ITEM_SCHEMA)
    assert not result.ok
    assert result.row_count == 3
    assert [(i.line, i.column, i.code) for i in result.issues] == [
        (3, "SKU", "duplicate_row"), (4, None, "duplicate_row"),
    ]
    assert all("line 2" in issue.message for issue in result.issues)
    assert result.headers == ("SKU", "Quantity", "Name")
    assert [record.cells for record in result.sample] == [("demo-a", "1", "Map")]
    assert not Item.objects.exists()


def test_successful_preview_caps_sample_and_requires_at_least_one_row():
    header = b"SKU,Quantity,Name\n"
    raw = header + b"".join(f"DEMO-{i},{i},Map\n".encode() for i in range(12))
    preview = preview_csv(BytesIO(raw), ITEM_SCHEMA)
    assert preview.ok and preview.row_count == 12 and len(preview.sample) == 10
    assert not Item.objects.exists()
    empty = preview_csv(BytesIO(header), ITEM_SCHEMA)
    assert not empty.ok and empty.issues[0].code == "no_rows"
