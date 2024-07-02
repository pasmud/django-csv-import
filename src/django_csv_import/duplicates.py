from django.db import models

from .issues import Issue
from .schema import ImportSchema


class DuplicateCheck:
    """Track exact matches for common, unconditional uniqueness rules."""

    def __init__(self, schema: ImportSchema):
        self.headers = {field: header for header, field in schema.columns.items()}
        meta = schema.model._meta
        groups = [(f.name,) for f in meta.concrete_fields if f.unique and f.name in self.headers]
        groups.extend(meta.unique_together)
        groups.extend(
            c.fields for c in meta.constraints
            if isinstance(c, models.UniqueConstraint)
            and c.fields and not c.expressions and c.condition is None
            and c.deferrable is None and not c.opclasses and not c.include and c.nulls_distinct is None
        )
        self.seen: dict[tuple[str, ...], dict[tuple, int]] = {
            fields: {} for fields in groups if set(fields) <= self.headers.keys()
        }

    def issues(self, instance: models.Model, line: int) -> list[Issue]:
        issues = []
        for fields, seen in self.seen.items():
            key = tuple(getattr(instance, name) for name in fields)
            if any(value is None for value in key):
                continue
            try:
                first = seen.setdefault(key, line)
            except TypeError:  # A custom scalar field can have an unhashable value.
                continue
            if first != line:
                columns = tuple(self.headers[name] for name in fields)
                issues.append(Issue(
                    "duplicate_row",
                    f"Duplicate value for {', '.join(columns)}; first seen on line {first}.",
                    line,
                    columns[0] if len(columns) == 1 else None,
                ))
        return issues
