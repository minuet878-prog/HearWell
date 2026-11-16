from screening.public_pages import page_at


def public_page(request):
    """The 公開頁面 being shown, for the layout's title, description and canonical address
    (spec #583). None on every other page, which keeps its own title."""
    page = page_at(request.path)
    if page is None:
        return {"public_page": None}
    # The address without query parameters, so /guide?edit=x is not a second page; https as in the
    # sitemap.
    return {"public_page": page, "canonical_url": f"https://{request.get_host()}{page.path}"}
