import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.utils import get_random_secret_key
from django.test import SimpleTestCase
from django.urls import Resolver404, resolve


class DevChecksTests(SimpleTestCase):
    """Spec docs/specs/phase-00/phase0_dev_checks.md, acceptance 2-9 and the Python version."""

    ROOT = Path(__file__).resolve().parent.parent.parent
    # Settings are computed when the module loads, so DEBUG=False is checked in a fresh process.
    # Only settings are read; nothing touches the database.
    DUMP = """
import json, sys
if sys.argv[1] == "without-toolbar":
    sys.modules["debug_toolbar"] = None  # as if requirements-dev.txt was not installed
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.test import Client
from django.urls import Resolver404, resolve
call_command("check")
try:
    resolve("/__debug__/render_panel/")
    debug_url = True
except Resolver404:
    debug_url = False
# An API URL: answers 403 without touching the database or static files.
response = Client().get("/api/questionnaires/", secure=True, HTTP_HOST="localhost")
print(json.dumps({
    "debug_url": debug_url,
    "hsts_header": response.headers.get("Strict-Transport-Security"),
    "apps": settings.INSTALLED_APPS,
    "middleware": settings.MIDDLEWARE,
    "hsts_seconds": getattr(settings, "SECURE_HSTS_SECONDS", 0),
    "hsts_subdomains": getattr(settings, "SECURE_HSTS_INCLUDE_SUBDOMAINS", False),
    "hsts_preload": getattr(settings, "SECURE_HSTS_PRELOAD", False),
    "silenced": settings.SILENCED_SYSTEM_CHECKS,
}))
"""

    def _run(self, args, debug, module="config.settings"):
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": module,
            "DEBUG": "True" if debug else "False",
            # A throwaway key for this process only; never written anywhere.
            "SECRET_KEY": get_random_secret_key(),
            # Production settings refuse to start without it; DUMP's request uses this host.
            "ALLOWED_HOSTS": "localhost",
        }
        return subprocess.run(
            [sys.executable, *args], cwd=self.ROOT, env=env, capture_output=True, text=True
        )

    def _settings(self, debug, toolbar="as-installed", module="config.settings"):
        result = self._run(["-c", self.DUMP, toolbar], debug, module)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def _uses_toolbar(self, dumped):
        return "debug_toolbar" in dumped["apps"] or any(
            m.startswith("debug_toolbar") for m in dumped["middleware"]
        )

    # 2, 6
    def test_production_settings(self):
        dumped = self._settings(debug=False)
        self.assertFalse(self._uses_toolbar(dumped))
        self.assertFalse(dumped["debug_url"])
        self.assertEqual(dumped["hsts_header"], "max-age=3600; includeSubDomains")
        self.assertEqual(dumped["hsts_seconds"], 3600)
        self.assertIs(dumped["hsts_subdomains"], True)
        self.assertIs(dumped["hsts_preload"], False)

    # 4, 7
    def test_debug_without_dev_packages_still_works(self):
        dumped = self._settings(debug=True, toolbar="without-toolbar")
        self.assertFalse(self._uses_toolbar(dumped))
        self.assertFalse(dumped["debug_url"])
        self.assertIsNone(dumped["hsts_header"])
        self.assertEqual(dumped["hsts_seconds"], 0)

    # 3
    def test_tests_never_load_toolbar(self):
        # Set DEBUG=True explicitly instead of relying on a local .env.
        dev = self._settings(debug=True)
        if not self._uses_toolbar(dev):
            self.skipTest("requirements-dev.txt is not installed, nothing to leave out")
        self.assertTrue(dev["debug_url"])
        tests = self._settings(debug=True, module="config.test_settings")
        self.assertFalse(self._uses_toolbar(tests))
        self.assertFalse(tests["debug_url"])
        self.assertNotIn("debug_toolbar", settings.INSTALLED_APPS)
        self.assertFalse([m for m in settings.MIDDLEWARE if m.startswith("debug_toolbar")])
        with self.assertRaises(Resolver404):
            resolve("/__debug__/render_panel/")

    # 5
    def test_toolbar_only_in_dev_requirements(self):
        production = (self.ROOT / "requirements.txt").read_text(encoding="utf-8")
        dev = (self.ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertNotIn("debug-toolbar", production.lower())
        self.assertEqual(dev.splitlines()[0], "-r requirements.txt")
        self.assertRegex(dev, r"(?m)^django-debug-toolbar==\d+\.\d+\.\d+$")

    # 8
    def test_deploy_check_passes_with_warnings_as_errors(self):
        result = self._run(["manage.py", "check", "--deploy", "--fail-level", "WARNING"], False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no issues (1 silenced)", result.stdout)
        self.assertEqual(self._settings(debug=False)["silenced"], ["security.W021"])

    # 9
    def test_build_runs_deploy_check_before_anything_changes(self):
        lines = (self.ROOT / "build.sh").read_text(encoding="utf-8").splitlines()
        self.assertIn("set -o errexit", lines)
        check = lines.index("python manage.py check --deploy --fail-level WARNING")
        for step in (
            "npm run build --prefix frontend",
            "python manage.py collectstatic --no-input",
            "python manage.py migrate",
            "python manage.py loaddata questions_fixture.json",
        ):
            with self.subTest(step=step):
                self.assertLess(check, lines.index(step))

    def test_build_seeds_questionnaires_after_the_fixture(self):
        # Issue #103: one generic seed after loaddata, so fixed fixture ids are taken first.
        lines = (self.ROOT / "build.sh").read_text(encoding="utf-8").splitlines()
        seed = lines.index("python manage.py seed_questionnaires")
        self.assertLess(lines.index("python manage.py loaddata questions_fixture.json"), seed)
        script = "\n".join(lines)
        self.assertNotIn("seed_hhia_s", script)
        self.assertNotIn("seed_ssq12", script)

    def test_production_python_matches_tests(self):
        pinned = (self.ROOT / ".python-version").read_text(encoding="utf-8").strip()
        self.assertEqual(pinned, platform.python_version())


class AllowedHostsTests(SimpleTestCase):
    """Spec docs/specs/phase-06/phase6_allowed_hosts.md, acceptance 1-5 and 8-10."""

    ROOT = Path(__file__).resolve().parent.parent.parent
    # Settings are computed when the module loads, so each case runs in a fresh process.
    # dotenv is stubbed out: a local .env must not fill in the variable the test leaves unset.
    LOAD = """
import json, sys, types
dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules["dotenv"] = dotenv
from django.core.exceptions import ImproperlyConfigured
try:
    import config.settings
except ImproperlyConfigured as error:
    print(json.dumps({"error": str(error)}))
else:
    print(json.dumps({"hosts": config.settings.ALLOWED_HOSTS}))
"""

    def _run(self, args, hosts, debug):
        env = {
            **os.environ,
            "DEBUG": "True" if debug else "False",
            # A throwaway key for this process only; never written anywhere.
            "SECRET_KEY": get_random_secret_key(),
        }
        env.pop("ALLOWED_HOSTS", None)
        if hosts is not None:
            env["ALLOWED_HOSTS"] = hosts
        return subprocess.run(
            [sys.executable, *args], cwd=self.ROOT, env=env, capture_output=True, text=True
        )

    def _load(self, hosts, debug=False):
        result = self._run(["-c", self.LOAD], hosts, debug)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    # 1, 2
    def test_production_rejects_empty_values(self):
        for value in ("", "   ", ","):
            with self.subTest(value=value):
                error = self._load(value)["error"]
                self.assertIn("ALLOWED_HOSTS", error)
                self.assertIn("是空的", error)

    # 3
    def test_spaces_around_hosts_are_removed(self):
        loaded = self._load("hearwell.onrender.com, localhost")
        self.assertEqual(loaded["hosts"], ["hearwell.onrender.com", "localhost"])

    # 4
    def test_empty_items_are_dropped(self):
        self.assertEqual(self._load("a.com,,b.com,")["hosts"], ["a.com", "b.com"])

    # 5
    def test_local_default_when_unset(self):
        self.assertEqual(self._load(None, debug=True)["hosts"], ["127.0.0.1", "localhost"])

    # 8
    def test_production_requires_the_variable(self):
        error = self._load(None)["error"]
        self.assertIn("ALLOWED_HOSTS", error)
        self.assertIn("缺少", error)

    # 9
    def test_local_rejects_empty_value(self):
        error = self._load("", debug=True)["error"]
        self.assertIn("ALLOWED_HOSTS", error)
        self.assertIn("是空的", error)

    # 10
    def test_render_value_passes_deploy_check(self):
        result = self._run(
            ["manage.py", "check", "--deploy", "--fail-level", "WARNING"],
            "hearwell.onrender.com",
            debug=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
