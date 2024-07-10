from dataclasses import dataclass
from typing import BinaryIO

from django.db import IntegrityError, router, transaction

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


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Outcome of an apply attempt; failed imports always report zero created rows."""

    row_count: int
    created_count: int
    issues: tuple[Issue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def import_csv(source: BinaryIO, schema: ImportSchema) -> ImportResult:
    """Validate a fresh upload and insert all rows in one database transaction."""
    using = router.db_for_write(schema.model)
    line = None
    row_count = 0
    try:
        with transaction.atomic(using=using):
            validation = validate(source, schema)
            row_count = validation.row_count
            if validation.issues:
                return ImportResult(row_count, 0, validation.issues)
            for row in validation.rows:
                line = row.record.line
                row.form.instance.save(using=using, force_insert=True)
            line = None  # An error at transaction commit need not identify a row.
    except IntegrityError:
        return ImportResult(row_count, 0, (Issue(
            "integrity", "The database rejected the import. No rows were saved.", line,
        ),))
    return ImportResult(row_count, row_count, ())
