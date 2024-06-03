from io import BytesIO

import pytest

from django_csv_import.csv_input import InputError, Limits, Record, read_csv


def test_bom_quoted_cells_blank_lines_and_physical_record_positions():
    raw = '\ufeffName,Notes\r\n"Mira, Jr.","first\r\nsecond"\r\n\r\nSol,last\r\n'.encode()
    table = read_csv(BytesIO(raw), Limits(max_bytes=len(raw), max_rows=2))
    assert table.header == Record(1, ("Name", "Notes"))
    assert table.rows == (Record(2, ("Mira, Jr.", "first\r\nsecond")), Record(5, ("Sol", "last")))


class ShortReads(BytesIO):
    def read(self, size=-1):
        return super().read(min(2, size))


def test_byte_limit_stops_at_first_excess_byte_even_with_short_reads():
    stream = ShortReads(b"Name\n" + b"a" * 100)
    with pytest.raises(InputError) as caught:
        read_csv(stream, Limits(max_bytes=9))
    assert caught.value.issue.code == "too_large"
    assert stream.tell() == 10


@pytest.mark.parametrize(
    ("raw", "code", "line"),
    [
        (b"\n", "empty", None),
        (b"Name\n\xff", "encoding", None),
        (b"Name\nA\0B", "nul", None),
        (b'Name\n"unclosed\nrecord', "csv", 2),
        (b"Name\nOne\n\nTwo", "too_many_rows", 4),
    ],
)
def test_input_failures(raw, code, line):
    with pytest.raises(InputError) as caught:
        read_csv(BytesIO(raw), Limits(max_rows=1))
    assert (caught.value.issue.code, caught.value.issue.line) == (code, line)
