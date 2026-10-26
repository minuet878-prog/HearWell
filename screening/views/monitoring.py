from django.http import Http404


class MonitoringTestError(Exception):
    """Raised on purpose so an admin can check that error monitoring reaches Sentry."""


def monitoring_test(request):
    if not request.user.is_superuser:
        raise Http404
    raise MonitoringTestError
