import sentry_sdk


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
