import os

import django
import pytest
from django.core.management import call_command
from django.db import connection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
django.setup()


@pytest.fixture(scope="session")
def sqlite_database(tmp_path_factory):
    connection.settings_dict["NAME"] = str(tmp_path_factory.mktemp("sqlite") / "tests.sqlite3")
    call_command("migrate", run_syncdb=True, verbosity=0, interactive=False)
    yield
    connection.close()


@pytest.fixture
def database(sqlite_database):
    yield
    call_command("flush", verbosity=0, interactive=False)
