SECRET_KEY = "local-test-only-placeholder"
INSTALLED_APPS = ["tests"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
