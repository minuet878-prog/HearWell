def classify(total_score):
    if total_score < 0 or total_score > 40:
        return {"text": "不合規的分數", "color": "danger"}
    elif total_score <= 8:
        return {"text": "無/極輕微影響", "color": "success"}
    elif total_score <= 24:
        return {"text": "輕度到中度影響", "color": "warning"}
    else:
        return {"text": "顯著影響", "color": "danger"}
