import copy
import logging
import sys
import traceback
from urllib.parse import urlsplit, urlunsplit

import sentry_sdk
from django.urls import Resolver404, resolve


def _route(url):
    # A share, a reminder's cancel link and a reset link carry their token in the path; the route
    # ("shared/<str:token>/report") still says which page broke.
    parts = urlsplit(url)
    try:
        route = resolve(parts.path).route
    except Resolver404:
        # A token link cut short or with a slash added: its path may still hold the token.
        route = "<no-route>"
    return urlunsplit((parts.scheme, parts.netloc, f"/{route}", "", ""))


def _scrub(event, hint):
    # Error messages can carry user data (e.g. a database error repeats the clashing username);
    # the type and the place in the code are kept.
    for exception in event.get("exception", {}).get("values", []):
        exception.pop("value", None)
    # Only the path and method of the request: headers carry the CSRF token (X-CSRFToken is not
    # on Sentry's own list), and the query string is not needed to find the error.
    request = event.get("request", {})
    request.pop("headers", None)
    request.pop("query_string", None)
    if "url" in request:
        request["url"] = _route(request["url"])
    # A logger.error() call is sent as its template only ("Score %s out of range ..."), without
    # the values filled in. Keep logging with %s: an f-string puts the data into the template.
    logentry = event.get("logentry", {})
    logentry.pop("formatted", None)
    logentry.pop("params", None)
    return event


def init(dsn, transport=None):
    sentry_sdk.init(
        dsn=dsn,
        transport=transport,
        send_default_pii=False,  # no IP, cookies or user
        max_request_body_size="never",  # no form data (answers, passwords)
        include_local_variables=False,  # no variable values (answers, scores)
        max_breadcrumbs=0,  # no earlier log lines riding along with an error
        auto_session_tracking=False,  # errors only, no usage data per request
        before_send=_scrub,
    )


class WithoutErrorWords(logging.Formatter):
    """settings.LOGGING's: an error's type and where it happened, without its words (they can
    hold an email), as _scrub sends it to Sentry."""

    def format(self, record):
        # The message's template only, without the values filled in, as _scrub sends it. A copy:
        # the same record also goes to Sentry.
        record = copy.copy(record)
        record.args = None
        return super().format(record)

    def formatException(self, exc_info):
        kind, _, trace = exc_info
        where = "".join(traceback.format_tb(trace))
        return f"Traceback (most recent call last):\n{where}{kind.__qualname__}"


class StderrHandler(logging.StreamHandler):
    """To stderr as it is when each line is written, like Python's own last-resort handler, where
    the site's logs went before settings.LOGGING."""

    def __init__(self, level=logging.NOTSET):
        logging.Handler.__init__(self, level)

    @property
    def stream(self):
        return sys.stderr
