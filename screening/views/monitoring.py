from django.db import Error, connection
from django.http import Http404, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


class MonitoringTestError(Exception):
    """Raised on purpose so an admin can check that error monitoring reaches Sentry."""


def monitoring_test(request):
    if not request.user.is_superuser:
        raise Http404
    raise MonitoringTestError


@never_cache
@require_safe
def uptime_check(request):
    """運作檢查 (spec #561): an outside monitor opens this every minute to learn whether the
    site is running; it shows no one's data."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        text, status = "ok", 200
    except Error:
        # Answered here, not raised: the monitor's own alert says the site is down, and an
        # error sent to Sentry every minute would bury the real ones.
        text, status = "database unavailable", 503
    response = HttpResponse(text, content_type="text/plain; charset=utf-8", status=status)
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response
