import csv
import io
from dataclasses import dataclass
from typing import BinaryIO

from .issues import Issue


@dataclass(frozen=True, slots=True)
class Limits:
    """Maximum upload bytes, data records, and optionally decoded cell characters."""

    max_bytes: int = 1024 * 1024
    max_rows: int = 1000
    max_cell_chars: int | None = None

    def __post_init__(self) -> None:
        for value in (self.max_bytes, self.max_rows):
            if type(value) is not int or value < 1:
                raise ValueError("CSV limits must be positive integers.")
        if self.max_cell_chars is not None and (type(self.max_cell_chars) is not int or self.max_cell_chars < 1):
            raise ValueError("max_cell_chars must be a positive integer or None.")


@dataclass(frozen=True, slots=True)
class Record:
    line: int
    cells: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Table:
    header: Record
    rows: tuple[Record, ...]


class InputError(Exception):
    def __init__(self, issue: Issue):
        super().__init__(issue.message)
        self.issue = issue


def read_csv(source: BinaryIO, limits: Limits) -> Table:
    """Read a fresh binary stream; stop after at most max_bytes + 1 bytes."""
    data = bytearray()
    while chunk := source.read(min(64 * 1024, limits.max_bytes + 1 - len(data))):
        if not isinstance(chunk, bytes):
            raise TypeError("CSV input must be a binary stream.")
        data.extend(chunk)
        if len(data) > limits.max_bytes:
            raise InputError(Issue("too_large", f"CSV exceeds {limits.max_bytes} bytes."))

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError(Issue("encoding", "CSV must be valid UTF-8.")) from exc
    if "\0" in text:
        raise InputError(Issue("nul", "CSV must not contain NUL characters."))

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    header = None
    rows = []
    while True:
        line = reader.line_num + 1
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            raise InputError(Issue("csv", f"Cannot read CSV record: {exc}.", line)) from exc

        if not cells:
            continue
        if header is not None and len(rows) == limits.max_rows:
            raise InputError(Issue("too_many_rows", f"CSV exceeds the data row limit ({limits.max_rows}).", line))
        if (max_chars := limits.max_cell_chars) is not None:
            for position, cell in enumerate(cells, start=1):
                if len(cell) > max_chars:
                    raise InputError(Issue(
                        "cell_too_long", f"Cell {position} exceeds {max_chars} characters.", line,
                    ))
        if header is None:
            header = Record(line, tuple(cells))
        else:
            rows.append(Record(line, tuple(cells)))

    if header is None:
        raise InputError(Issue("empty", "CSV must contain a header."))
    return Table(header, tuple(rows))
