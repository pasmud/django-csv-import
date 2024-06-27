from dataclasses import dataclass
from typing import BinaryIO

from django import forms
from django.core.exceptions import NON_FIELD_ERRORS

from .csv_input import InputError, Record, read_csv
from .issues import Issue
from .schema import ImportSchema


@dataclass(frozen=True, slots=True)
class ValidatedRow:
    record: Record
    form: forms.ModelForm


@dataclass(frozen=True, slots=True)
class Validation:
    row_count: int = 0
    headers: tuple[str, ...] = ()
    rows: tuple[ValidatedRow, ...] = ()
    issues: tuple[Issue, ...] = ()


def validate(source: BinaryIO, schema: ImportSchema) -> Validation:
    try:
        table = read_csv(source, schema.limits)
    except InputError as exc:
        return Validation(issues=(exc.issue,))

    row_count = len(table.rows)
    issues = list(schema._header_issues(table.header))
    if issues:
        return Validation(row_count=row_count, issues=tuple(issues))
    if not row_count:
        return Validation(issues=(Issue("no_rows", "CSV must contain at least one data row."),))

    headers = table.header.cells
    fields = tuple(schema.columns[header] for header in headers)
    header_by_field = dict(zip(fields, headers, strict=True))
    rows = []
    for record in table.rows:
        if len(record.cells) != len(fields):
            issues.append(Issue(
                "row_width", f"Expected {len(fields)} cells, found {len(record.cells)}.", record.line,
            ))
            continue
        form = schema.form_class(data=dict(zip(fields, record.cells, strict=True)))
        if form.is_valid():
            rows.append(ValidatedRow(record, form))
            continue
        for field, errors in form.errors.as_data().items():
            column = None if field == NON_FIELD_ERRORS else header_by_field.get(field)
            for error in errors:
                for message in error.messages:
                    issues.append(Issue(error.code or "invalid", message, record.line, column))

    return Validation(row_count, headers, tuple(rows), tuple(issues))
