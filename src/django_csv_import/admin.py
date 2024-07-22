from django import forms
from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import Http404, HttpResponseRedirect
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


class CSVImportAdminMixin:
    """Add a CSRF-protected, add-permission-only CSV view to a ModelAdmin."""

    csv_import_schema: ImportSchema | None = None
    change_list_template = "django_csv_import/change_list.html"
    csv_import_template = "django_csv_import/import.html"

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
        if self.csv_import_schema is not None and self.has_add_permission(request):
            context["csv_import_url"] = self._csv_reverse("import_csv")
        return super().changelist_view(request, extra_context=context)

    @method_decorator(require_http_methods(["GET", "POST"]))
    def csv_import_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        schema = self.csv_import_schema
        if schema is None:
            raise Http404
        if schema.model is not self.model:
            raise ImproperlyConfigured("The CSV import schema must target this ModelAdmin's model.")

        request.current_app = self.admin_site.name
        can_list = self.has_view_or_change_permission(request)
        list_url = self._csv_reverse("changelist") if can_list else None
        result = None
        preview = None
        form = UploadForm()
        if request.method == "POST":
            form = UploadForm(request.POST, request.FILES)
            if form.is_valid():
                upload = form.cleaned_data["upload"]
                if upload.size > schema.limits.max_bytes:
                    form.add_error("upload", f"CSV exceeds {schema.limits.max_bytes} bytes.")
                elif form.cleaned_data["mode"] == "preview":
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
            "limits": schema.limits,
            "headers": schema.columns.keys(),
            "list_url": list_url,
        })
