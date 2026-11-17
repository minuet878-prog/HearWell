from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET

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
