from django import template

from screening.scoring import level_to_color as get_color

register = template.Library()


@register.filter
def level_to_color(value):
    return get_color(value)
