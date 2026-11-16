from django.templatetags.static import static

from screening.public_pages import PREVIEW_IMAGE, PROTOCOL, SITE_DESCRIPTION, page_at


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
