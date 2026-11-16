from django.contrib.sitemaps import Sitemap
from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_safe

from screening.public_pages import public_urls


class PublicPagesSitemap(Sitemap):
    # The addresses only: Google ignores changefreq and priority, and takes lastmod only when it is
    # always right (spec #583). The host is the request's, as the sites framework is not installed.
    protocol = "https"

    def items(self):
        return public_urls()

    def location(self, item):
        return item


@require_safe
def robots_txt(request):
    """What search engines read first (spec #583): every address may be read, and where the
    sitemap is. Nothing is kept out here: a page kept out of robots.txt is never read, so its
    noindex is never seen and the address may still show in results (ADR 0062)."""
    lines = (
        "User-agent: *",
        "Allow: /",
        "",
        f"Sitemap: {PublicPagesSitemap.protocol}://{request.get_host()}{reverse('sitemap')}",
    )
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")
