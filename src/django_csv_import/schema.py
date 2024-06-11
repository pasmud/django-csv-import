from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from django import forms
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models

from .csv_input import Limits, Record
from .issues import Issue


@dataclass(frozen=True, slots=True)
class ImportSchema:
    """Bind exact CSV headers to all fields of an explicit, scalar ModelForm."""

    form_class: type[forms.ModelForm]
    columns: Mapping[str, str]
    limits: Limits = Limits()

    def __post_init__(self) -> None:
        form = self.form_class
        if not isinstance(form, type) or not issubclass(form, forms.ModelForm):
            raise ImproperlyConfigured("CSV import requires a ModelForm class.")
        explicit = form._meta.fields
        if not isinstance(explicit, (tuple, list)) or not explicit or form._meta.exclude:
            raise ImproperlyConfigured("CSV import requires explicit ModelForm Meta.fields.")
        if form._meta.model is None:
            raise ImproperlyConfigured("CSV import requires a ModelForm with Meta.model.")

        columns = dict(self.columns)
        if not columns or any(
            not isinstance(header, str) or not header.strip() or "\0" in header for header in columns
        ):
            raise ImproperlyConfigured("CSV import headers must be nonblank strings.")
        targets = tuple(columns.values())
        if (
            any(not isinstance(name, str) for name in targets)
            or len(set(targets)) != len(targets)
            or len(explicit) != len(targets)
            or set(targets) != set(explicit)
            or set(targets) != set(form.base_fields)
        ):
            raise ImproperlyConfigured("CSV headers must map one-to-one onto the form fields.")

        for name in targets:
            try:
                field = self.model._meta.get_field(name)
            except FieldDoesNotExist as exc:
                raise ImproperlyConfigured(f"CSV target {name!r} is not a model field.") from exc
            if (
                name != field.name
                or not field.concrete
                or not field.editable
                or field.primary_key
                or field.is_relation
                or field.generated
                or isinstance(field, models.FileField)
            ):
                raise ImproperlyConfigured(f"CSV target {name!r} is not an editable scalar field.")
            form_field = form.base_fields[name]
            if form_field.disabled or isinstance(
                form_field.widget,
                (
                    forms.CheckboxInput, forms.MultiWidget, forms.SelectMultiple,
                    forms.NullBooleanSelect, forms.FileInput, forms.PasswordInput,
                ),
            ):
                raise ImproperlyConfigured(f"CSV target {name!r} needs a single-value text widget.")
        object.__setattr__(self, "columns", MappingProxyType(columns))

    @property
    def model(self) -> type[models.Model]:
        return self.form_class._meta.model

    def _header_issues(self, header: Record) -> tuple[Issue, ...]:
        counts = Counter(header.cells)
        issues = []
        if any(count > 1 for count in counts.values()):
            issues.append(Issue("duplicate_header", "CSV headers must be unique.", header.line))
        if counts.keys() - self.columns.keys():
            issues.append(Issue("unknown_header", "CSV contains unexpected headers.", header.line))
        for column in self.columns:
            if column not in counts:
                issues.append(Issue("missing_header", "Required header is absent.", header.line, column))
        return tuple(issues)
