def classify(total_score):
    if total_score < 0 or total_score > 40:
        return "不合規的分數"
    elif total_score <= 8:
        return "無/極輕微影響"
    elif total_score <= 24:
        return "輕度到中度影響"
    elif total_score <= 40:
        return "顯著影響"
