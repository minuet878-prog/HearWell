def classify(total_score):
    if total_score < 0 or total_score > 40:
        raise ValueError(f"{total_score}是不合規的分數")
    elif total_score <= 8:
        return {"text": "無/極輕微影響", "level": "normal"}
    elif total_score <= 24:
        return {"text": "輕度到中度影響", "level": "mild_to_moderate"}
    else:
        return {"text": "顯著影響", "level": "severe"}


def level_to_color(level):
    colors = {
        "normal": "success",
        "mild_to_moderate": "warning",
        "severe": "danger",
    }
    return colors[level]
