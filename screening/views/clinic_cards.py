import segno
from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET

from screening.clinic_cards import CAMERA, CARDS, FREE

# 診間小卡 (spec #677, ADR 0066): where each card's address lands, with the card's mark that the
# landing page counts and then takes off. Fixed here, never read from the request, so an address
# cannot be turned into a way off the site; a new landing changes only this table.
LANDINGS = {
    "elder": ("questionnaire_list", "clinic-elder"),
    "family": ("family_guide", "clinic-family"),
}


@require_GET
def card_address(request, card):
    page, mark = LANDINGS[card]
    # 302, not 301: browsers keep a 301, and a later landing would not reach cards already scanned.
    return redirect(f"{reverse(page)}?via={mark}")


@require_GET
def print_page(request):
    """One A4 sheet of 10 cards of the kind chosen, the elder card unless the family card is."""
    card = request.GET.get("card") if request.GET.get("card") in CARDS else "elder"
    choices = [(key, each.choice) for key, each in CARDS.items()]
    return render(
        request,
        "screening/clinic_cards.html",
        {
            "card": card,
            "choices": choices,
            "words": CARDS[card],
            "free": FREE,
            "camera": CAMERA,
            "qr_code": qr_code(CARDS[card].address),
            "sheet": range(10),
        },
    )


def qr_code(address_name):
    """The card's QR code as an SVG drawn here (no outside service), holding its 小卡網址 on the
    live site, never the address this page was opened at: printed from a laptop at home, it
    still opens tingpal.tw. None without SITE_URL, so no card goes out pointing nowhere."""
    if not settings.SITE_URL:
        return None
    address = settings.SITE_URL + reverse(address_name)
    # Medium error correction and the standard 4-square white border (ADR 0066, the grill).
    code = segno.make(address, error="m", micro=False)
    svg = code.svg_inline(
        border=4, dark="#000", light="#fff", omitsize=True, title=f"QR code：{address}"
    )
    return mark_safe(svg.replace("<svg ", '<svg role="img" ', 1))
