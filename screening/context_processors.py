from urllib.parse import urlencode

from django.templatetags.static import static
from django.urls import reverse

from screening.public_pages import PREVIEW_IMAGE, PROTOCOL, SITE_DESCRIPTION, page_at

# Spec #633 Q5: the pages whose footer link names which one, by its code; every other page is
# named by its kind alone, so no record number or share code goes with it.
NAMED_BY_CODE = {"guide_chapter": "chapter", "qa_answer": "code"}


def feedback_link(request):
    """The footer's 意見回饋 link (spec #633, #636): which page it is on (views.feedback turns it
    into words) and the way back to it, which is never kept."""
    match = request.resolver_match
    page = match.url_name if match and match.url_name else ""
    if page in NAMED_BY_CODE:
        page = f"{page}:{match.kwargs[NAMED_BY_CODE[page]]}"
    query = urlencode({"page": page, "next": request.get_full_path()})
    return {"feedback_url": f"{reverse('feedback')}?{query}"}


def page_head(request):
    """The 公開頁面 being shown, for the layout's title, description and canonical address, and
    what a LINE preview of any page shows (spec #583). public_page is None on every other page,
    which keeps its own title and takes the site's description in its preview."""
    host = f"{PROTOCOL}://{request.get_host()}"
    # Full address, as og:image needs; the static file's name changes with its content.
    preview = {"preview_image_url": f"{host}{static(PREVIEW_IMAGE)}"}
    page = page_at(request.path)
    if page is None:
        return {"public_page": None, "preview_description": SITE_DESCRIPTION, **preview}
    return {
        "public_page": page,
        # The address without query parameters, so /guide?edit=x is not a second page.
        "canonical_url": f"{host}{page.path}",
        "preview_description": page.description,
        **preview,
    }
