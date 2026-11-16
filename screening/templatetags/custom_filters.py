from django import template
from django.utils.safestring import mark_safe

from screening.audiogram import degree_level as get_degree_level
from screening.middleware import OPEN_PAGES

register = template.Library()


class CaptureNode(template.Node):
    # Its nodelist, like any Node's, is searched for {% block %}: a page's title block inside
    # still overrides the layout's.
    def __init__(self, nodelist, name):
        self.nodelist = nodelist
        self.name = name

    def render(self, context):
        # Already escaped as it rendered, so shown again as it is.
        context[self.name] = mark_safe(self.nodelist.render(context).strip())
        return ""


@register.tag
def capture(parser, token):
    """{% capture name %}…{% endcapture %}: render once, use as {{ name }} several times.
    layout.html shows a page's title in <title> and in its LINE preview (spec #583, #590)."""
    _tag, name = token.split_contents()
    nodelist = parser.parse(("endcapture",))
    parser.delete_first_token()
    return CaptureNode(nodelist, name)


@register.filter
def degree_level(value):
    # Badge colour of an audiogram degree; the mapping lives in screening.audiogram (rule 9).
    return get_degree_level(value)


@register.filter
def step_segments(step, total):
    # step_progress.html: one flag per step bar segment, set for this step and the ones before.
    return [number <= step for number in range(1, total + 1)]


@register.filter
def asks_about_guest_results(url_name):
    # #497: layout.html's guest-ask.js, which takes someone signed in with guest results here to
    # the save page's question. On the home page and the pages past the consent; not on the save
    # page itself, nor the pages open before agreeing (the save page needs the consent, and the
    # notice or deleting the account must stay reachable), nor 確認本人, a step in the middle of
    # adding or removing a sign-in method or deleting the account, which taken away there was
    # lost (#506 acceptance); the question waits for the page the step ends on.
    return url_name == "index" or url_name not in OPEN_PAGES | {"guest_save", "confirm_identity"}
