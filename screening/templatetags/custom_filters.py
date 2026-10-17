from django import template

from screening.audiogram import degree_level as get_degree_level

register = template.Library()


@register.filter
def degree_level(value):
    # Badge colour of an audiogram degree; the mapping lives in screening.audiogram (rule 9).
    return get_degree_level(value)
