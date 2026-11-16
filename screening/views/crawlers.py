from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_safe


@require_safe
def robots_txt(request):
    """What search engines read first (spec #583): every address may be read, and where the
    sitemap is. Nothing is kept out here: a page kept out of robots.txt is never read, so its
    noindex is never seen and the address may still show in results (ADR 0062)."""
    lines = (
        "User-agent: *",
        "Allow: /",
        "",
        # The sitemap's own protocol (PublicPagesSitemap) and the request's host.
        f"Sitemap: https://{request.get_host()}{reverse('sitemap')}",
    )
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")
