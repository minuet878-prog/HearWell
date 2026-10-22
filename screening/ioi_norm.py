"""IOI-HA's norm group and the record it comes from (ADR 0002), for the web form and API alike."""

from django.core import signing

from screening.scoring import ioi_ha_group

# Told to the user when a page's token cannot be trusted, web and API alike.
TOKEN_ERROR = "常模依據無法確認，請重新開啟問卷。"


def norm_bases(user):
    # The user's own unaided HHIA-S or HHIE-S records that can set the IOI-HA norm group.
    return user.submissions.valid_hhi().filter(wearing_hearing_aid=False)


def ioi_ha_norm(user, token=None):
    records = norm_bases(user).select_related("questionnaire")
    if token is None:
        basis = records.first()
    else:
        data = signing.loads(token, salt="screening.ioi-norm")
        if data["user"] != user.pk:
            raise signing.BadSignature("Wrong norm owner")
        basis = records.filter(pk=data["basis"]).first() if data["basis"] else None
        if data["basis"] and basis is None:
            raise signing.BadSignature("Unavailable norm basis")
    total = None if basis is None else basis.total_answer_score
    return {"norm_group": ioi_ha_group(total), "norm_basis": basis}


def norm_token(user, norm):
    return signing.dumps(
        {"user": user.pk, "basis": norm["norm_basis"].pk if norm["norm_basis"] else None},
        salt="screening.ioi-norm",
    )
