import json
import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path
from unittest import mock

import sentry_sdk
from django.core.handlers.wsgi import WSGIHandler
from django.core.management.utils import get_random_secret_key
from django.core.signals import request_finished, request_started
from django.db import IntegrityError, close_old_connections
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from sentry_sdk.transport import Transport

from config import monitoring
from screening import scoring
from screening.models import Question, Questionnaire, User
from screening.tests.helpers import consented_user

FAKE_DSN = "https://public@o0.ingest.de.sentry.io/0"


class CaptureTransport(Transport):
    """Keeps what would have been sent to Sentry, so tests can read it without a network."""

    def __init__(self, options=None):
        super().__init__(options)
        self.envelopes = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)


class MonitoringTests(TestCase):
    """Spec docs/specs/phase-06/phase6_error_monitoring.md.

    Acceptance 1-4, 3a, 3b, 4a, 4b, 7 and 8."""

    PASSWORD = "Xk9#mPq2vLw"
    CSRF = "csrfsecretcsrfsecretcsrfsecret12"  # 32 letters and digits, like Django's own
    IP = "203.0.113.7"  # an address reserved for documentation

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(
            username="monitored_user", email="monitored@example.com", password=cls.PASSWORD
        )
        cls.admin = User.objects.create_superuser(username="site_admin", password=cls.PASSWORD)
        cls.admin.give_consent()
        cls.questionnaire = Questionnaire.objects.create(
            questionnaire_name="測試問卷", code="hhie-s"
        )
        cls.questions = [
            Question.objects.create(
                questionnaire=cls.questionnaire,
                question_number=number,
                question_text=f"題目{number}",
                category="emotional",
            )
            for number in (1, 2)
        ]

    def setUp(self):
        self.transport = CaptureTransport()
        monitoring.init(FAKE_DSN, transport=self.transport)
        self.addCleanup(sentry_sdk.init)  # back to a client that sends nothing
        # That client keeps recording breadcrumbs between tests; production calls init once at
        # start-up, so nothing is recorded before it. Start each test from the same clean state.
        for scope in (
            sentry_sdk.get_global_scope(),
            sentry_sdk.get_isolation_scope(),
            sentry_sdk.get_current_scope(),
        ):
            scope.clear_breadcrumbs()

    def _send(self, method, path, data=None, user=None, csrf=True):
        """Call Django the way gunicorn does: Sentry reads the URL, headers and cookies there,
        and the test client skips that layer."""
        if data is not None and csrf:
            data = {**data, "csrfmiddlewaretoken": self.CSRF}
        environ = getattr(RequestFactory(), method)(path, data or {}).environ
        cookies = {"csrftoken": self.CSRF}
        if user is not None:
            self.client.force_login(user)
            cookies["sessionid"] = self.client.cookies["sessionid"].value
        environ["HTTP_COOKIE"] = "; ".join(f"{name}={value}" for name, value in cookies.items())
        environ["REMOTE_ADDR"] = self.IP
        if csrf:
            environ["HTTP_X_CSRFTOKEN"] = self.CSRF  # what a browser sends with PUT
        status = []
        # Like the test client: keep the test's database connection open after the request.
        request_started.disconnect(close_old_connections)
        request_finished.disconnect(close_old_connections)
        try:
            b"".join(WSGIHandler()(environ, lambda line, headers: status.append(line)))
        finally:
            request_started.connect(close_old_connections)
            request_finished.connect(close_old_connections)
        return int(status[0].split()[0]), cookies.get("sessionid")

    def _events(self):
        sentry_sdk.flush()
        return [env.get_event() for env in self.transport.envelopes if env.get_event()]

    def _only_event(self):
        events = self._events()
        self.assertEqual(len(events), 1, events)
        return events[0], json.dumps(events[0], default=str)

    def _assert_no_personal_data(self, event, payload, *secrets):
        request = event["request"]
        self.assertEqual(request["method"], "POST")  # the WSGI layer was really there
        self.assertFalse(request.get("data"))
        self.assertNotIn("cookies", request)
        self.assertNotIn("headers", request)
        self.assertNotIn("user", event)
        self.assertNotIn('"vars"', payload)
        for secret in (self.PASSWORD, self.CSRF, self.IP, *secrets):
            self.assertNotIn(secret, payload)

    def _answer_url(self):
        return reverse("screening", args=[self.questionnaire.id])

    # 1
    def test_unhandled_error_is_sent_with_type_path_and_place(self):
        with mock.patch("screening.views.render", side_effect=RuntimeError("detail")):
            status, _ = self._send("get", f"{reverse('index')}?next=/secret-query")
        self.assertEqual(status, 500)
        event, payload = self._only_event()
        exception = event["exception"]["values"][-1]
        self.assertEqual(exception["type"], "RuntimeError")
        self.assertNotIn("value", exception)
        self.assertNotIn("detail", payload)
        self.assertNotIn("secret-query", payload)
        self.assertEqual(event["request"]["url"], "http://testserver/")
        self.assertEqual(event["request"]["method"], "GET")
        files = [frame["filename"] for frame in exception["stacktrace"]["frames"]]
        self.assertIn("screening/views.py", files)

    # 2
    def test_answer_error_sends_no_form_cookie_or_user(self):
        data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "wearing_hearing_aid": "True",
            "idempotency_key": str(uuid.uuid4()),
        }
        for i, question in enumerate(self.questions):
            data[f"form-{i}-question_id"] = str(question.id)
            data[f"form-{i}-score"] = "4"
        with mock.patch(
            "screening.views.AnswerFormSet.save", side_effect=RuntimeError("save failed")
        ):
            status, session_id = self._send("post", self._answer_url(), data, user=self.user)
        self.assertEqual(status, 500)
        event, payload = self._only_event()
        self._assert_no_personal_data(
            event,
            payload,
            session_id,
            data["idempotency_key"],
            "form-0-score",
            "monitored_user",
            "monitored@example.com",
        )

    # 3, 3a
    def test_register_error_sends_no_password_or_name_in_message(self):
        clash = IntegrityError(
            'duplicate key value violates unique constraint "x"\n'
            "DETAIL:  Key (username)=(newcomer_secret) already exists."
        )
        data = {
            "username": "newcomer_secret",
            "email": "newcomer_secret@example.com",
            "password1": self.PASSWORD,
            "password2": self.PASSWORD,
        }
        with mock.patch("screening.views.RegisterForm.save", side_effect=clash):
            status, _ = self._send("post", reverse("register"), data)
        self.assertEqual(status, 500)
        event, payload = self._only_event()
        self._assert_no_personal_data(event, payload, "newcomer_secret")
        exception = event["exception"]["values"][-1]
        self.assertEqual(exception["type"], "IntegrityError")
        self.assertTrue(exception["stacktrace"]["frames"])

    # 3
    def test_login_error_sends_no_password(self):
        with mock.patch(
            "django.contrib.auth.views.auth_login", side_effect=RuntimeError("login failed")
        ):
            status, _ = self._send(
                "post", reverse("login"), {"username": "monitored_user", "password": self.PASSWORD}
            )
        self.assertEqual(status, 500)
        event, payload = self._only_event()
        self._assert_no_personal_data(event, payload, "monitored_user")

    # 3b
    def test_logged_error_sends_only_the_template(self):
        # Seven digits: longer than the microseconds in a timestamp, so only a leak can match.
        self.assertEqual(scoring.classify(4242424, "hhie-s"), scoring.UNKNOWN)
        event, payload = self._only_event()
        self.assertEqual(
            event["logentry"], {"message": "Score %s out of range for questionnaire %r"}
        )
        self.assertNotIn("4242424", payload)
        self.assertNotIn("hhie-s", payload)
        self.assertFalse(event.get("breadcrumbs", {}).get("values"))

    # 3b
    def test_logs_before_the_error_do_not_ride_along(self):
        # Made at run time: Sentry also sends the source lines around each frame, so a value
        # written in this file would show up as code.
        secret = uuid.uuid4().hex

        def log_then_fail(*args, **kwargs):
            # Logged during the same request, just before the error.
            logging.getLogger("screening").warning("crumb %s", secret)
            raise RuntimeError("detail")

        with mock.patch("screening.views.render", side_effect=log_then_fail):
            self._send("get", reverse("index"))
        event, payload = self._only_event()
        self.assertNotIn(secret, payload)
        self.assertFalse(event.get("breadcrumbs", {}).get("values"))

    # 4a
    def test_no_usage_data_even_with_a_release(self):
        with mock.patch.dict(os.environ, {"SENTRY_RELEASE": "test-release"}):
            monitoring.init(FAKE_DSN, transport=self.transport)
        self.assertEqual(self._send("get", reverse("index"))[0], 200)
        sentry_sdk.get_client().close()
        self.assertEqual([item.type for env in self.transport.envelopes for item in env.items], [])

    # 4
    def test_normal_refusals_send_nothing(self):
        login = reverse("login")
        refusals = [
            (self._send("post", login, {"username": "monitored_user", "password": "x"}), 200),
            (self._send("put", login), 405),
            (self._send("get", "/no-such-page"), 404),
            (self._send("post", login, {"username": "a", "password": "b"}, csrf=False), 403),
            (self._send("get", reverse("result", args=[999999]), user=self.user), 404),
            (self._send("post", self._answer_url(), {"form-TOTAL_FORMS": "0"}, self.user), 200),
        ]
        self.assertEqual([status for (status, _), _ in refusals], [want for _, want in refusals])
        self.assertEqual(self._events(), [])

    # 7
    def test_test_page_is_404_for_everyone_but_admins(self):
        url = reverse("monitoring_test")
        self.assertEqual(self._send("get", url)[0], 404)
        self.assertEqual(self._send("get", url, user=self.user)[0], 404)
        self.assertEqual(self._events(), [])

    # 8
    def test_test_page_sends_a_test_error_for_admins(self):
        status, _ = self._send("get", reverse("monitoring_test"), user=self.admin)
        self.assertEqual(status, 500)
        event, payload = self._only_event()
        self.assertEqual(event["exception"]["values"][-1]["type"], "MonitoringTestError")
        self.assertNotIn("site_admin", payload)
        self.assertNotIn("user", event)


class MonitoringSwitchTests(SimpleTestCase):
    """Spec docs/specs/phase-06/phase6_error_monitoring.md, acceptance 5."""

    ROOT = Path(__file__).resolve().parent.parent.parent
    # Settings run when the module loads, so each case is a fresh process with dotenv stubbed:
    # a local .env must not fill in the variable the test leaves unset.
    LOAD = """
import json, sys, types
dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules["dotenv"] = dotenv
import config.settings
import sentry_sdk
print(json.dumps({"active": sentry_sdk.get_client().is_active()}))
"""

    def _active(self, dsn):
        env = {**os.environ, "DEBUG": "False", "SECRET_KEY": get_random_secret_key()}
        env.setdefault("ALLOWED_HOSTS", "localhost")
        env.pop("SENTRY_DSN", None)
        if dsn is not None:
            env["SENTRY_DSN"] = dsn
        result = subprocess.run(
            [sys.executable, "-c", self.LOAD],
            cwd=self.ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])["active"]

    def test_off_without_dsn(self):
        self.assertFalse(self._active(None))
        self.assertFalse(self._active(""))

    def test_on_with_dsn(self):
        self.assertTrue(self._active(FAKE_DSN))

    def test_off_in_this_test_run(self):
        # The monitoring tests swap in a client without a DSN afterwards; nothing can be sent.
        self.assertIsNone(sentry_sdk.get_client().transport)
