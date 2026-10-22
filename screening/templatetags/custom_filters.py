from django import template

from screening.audiogram import degree_level as get_degree_level

register = template.Library()


@register.filter
def degree_level(value):
    # Badge colour of an audiogram degree; the mapping lives in screening.audiogram (rule 9).
    return get_degree_level(value)


@register.filter
def step_segments(step, total):
    # step_progress.html: one flag per step bar segment, set for this step and the ones before.
    return [number <= step for number in range(1, total + 1)]
