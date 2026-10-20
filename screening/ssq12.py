"""Reviewed SSQ12-TW scale anchors (#79), Wang 2023."""


def scale_labels(number):
    return {9: ("混亂", "分開"), 11: ("不清晰", "清晰"), 12: ("非常專心", "輕鬆做到")}.get(
        number, ("完全不行", "輕鬆做到")
    )
