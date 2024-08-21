import csv

from django import forms
from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
)
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.utils.translation import ngettext
from django.views.decorators.http import require_http_methods

from .schema import ImportSchema
from .service import import_csv, preview_csv


class UploadForm(forms.Form):
    upload = forms.FileField(label="CSV file")
    mode = forms.ChoiceField(choices=(("preview", "Preview"), ("apply", "Import")))

    def __init__(self, *args, report_enabled=False, **kwargs):
        super().__init__(*args, **kwargs)
        if report_enabled:
            self.fields["mode"].choices += [("report", "Download validation report")]


class CSVImportAdminMixin:
    """Add a CSRF-protected, add-permission-only CSV view to a ModelAdmin."""

    csv_import_schema: ImportSchema | None = None
    csv_import_report_enabled = False
    change_list_template = "django_csv_import/change_list.html"
    csv_import_template = "django_csv_import/import.html"

    def get_csv_import_schema(self, request: HttpRequest) -> ImportSchema | None:
        """Select an import schema for this request; None disables imports."""
        return self.csv_import_schema

    def _csv_url_name(self, action):
        return f"{self.opts.app_label}_{self.opts.model_name}_{action}"

    def _csv_reverse(self, action):
        return reverse(f"admin:{self._csv_url_name(action)}", current_app=self.admin_site.name)

    def get_urls(self):
        return [
            path(
                "import-csv/",
                self.admin_site.admin_view(self.csv_import_view),
                name=self._csv_url_name("import_csv"),
            ),
            *super().get_urls(),
        ]

    def changelist_view(self, request, extra_context=None):
        context = dict(extra_context or {})
        if self.has_add_permission(request) and self.get_csv_import_schema(request) is not None:
            context["csv_import_url"] = self._csv_reverse("import_csv")
        return super().changelist_view(request, extra_context=context)

    @method_decorator(require_http_methods(["GET", "POST"]))
    def csv_import_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        schema = self.get_csv_import_schema(request)
        if schema is None:
            raise Http404
        if schema.model is not self.model:
            raise ImproperlyConfigured("The CSV import schema must target this ModelAdmin's model.")

        if request.method == "GET" and request.GET.get("download") == "template":
            response = HttpResponse(
                content_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="import-template.csv"'},
            )
            csv.writer(response).writerow(schema.columns)
            return response

        request.current_app = self.admin_site.name
        can_list = self.has_view_or_change_permission(request)
        list_url = self._csv_reverse("changelist") if can_list else None
        result = None
        preview = None
        form = UploadForm(report_enabled=self.csv_import_report_enabled)
        if request.method == "POST":
            form = UploadForm(request.POST, request.FILES, report_enabled=self.csv_import_report_enabled)
            if form.is_valid():
                upload = form.cleaned_data["upload"]
                mode = form.cleaned_data["mode"]
                if upload.size > schema.limits.max_bytes:
                    form.add_error("upload", f"CSV exceeds {schema.limits.max_bytes} bytes.")
                elif mode == "report":
                    report = preview_csv(upload, schema)
                    return JsonResponse({
                        "ok": report.ok,
                        "row_count": report.row_count,
                        "issues": [
                            {"line": issue.line, "column": issue.column, "code": issue.code}
                            for issue in report.issues
                        ],
                    }, headers={"Content-Disposition": 'attachment; filename="csv-validation-report.json"'})
                elif mode == "preview":
                    preview = result = preview_csv(upload, schema)
                else:
                    result = import_csv(upload, schema)
                    if result.ok:
                        count = result.created_count
                        message = ngettext("Imported %d row.", "Imported %d rows.", count) % count
                        self.message_user(request, message, messages.SUCCESS)
                        return HttpResponseRedirect(list_url or self._csv_reverse("import_csv"))

        return TemplateResponse(request, self.csv_import_template, {
            **self.admin_site.each_context(request),
            "title": f"Import CSV: {self.opts.verbose_name_plural}",
            "opts": self.opts,
            "form": form,
            "result": result,
            "preview": preview,
            "report_enabled": self.csv_import_report_enabled,
            "limits": schema.limits,
            "headers": schema.columns.keys(),
            "list_url": list_url,
        })
