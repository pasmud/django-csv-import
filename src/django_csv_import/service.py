from dataclasses import dataclass
from typing import BinaryIO

from .csv_input import Record
from .issues import Issue
from .schema import ImportSchema
from .validation import validate


@dataclass(frozen=True, slots=True)
class Preview:
    """Validation outcome and up to ten valid rows of raw CSV input."""

    row_count: int
    issues: tuple[Issue, ...]
    headers: tuple[str, ...]
    sample: tuple[Record, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def preview_csv(source: BinaryIO, schema: ImportSchema) -> Preview:
    """Run a read-only preview; the result never reserves database state."""
    validation = validate(source, schema)
    return Preview(
        validation.row_count,
        validation.issues,
        validation.headers,
        tuple(row.record for row in validation.rows[:10]),
    )
