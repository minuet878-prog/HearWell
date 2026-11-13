"""Each sign-in provider's words, and its name page (spec #505 Google, #506 LINE): a new provider
is one more entry in WORDS. Where it sends people and how its tokens are checked is oidc.PROVIDERS.

Google's words are the #507 mockup's (W4-W7, W10, W13-W16, D3; the ends of two changed by the
#539 mockup W8), LINE's the #539 mockup's (W1-W3, W7, W10, W11) and #506 acceptance 13, 14.
Where neither mockup has wording the entry says so: a draft for the owner."""

from dataclasses import dataclass

from screening.forms import GoogleNameForm, LineNameForm


@dataclass(frozen=True)
class ProviderWords:
    # Signing in (views/sign_in.py): the words a trip comes back with on the login page.
    # Technical details go to error monitoring only.
    cancelled: str
    unavailable: str
    # The name page waited too long.
    name_expired: str
    # Error monitoring keeps a log line's template only (config/monitoring.py), so each
    # provider's name is written into its own.
    not_answering_log: str
    rejected_log: str
    # The first time back, before the account is made: the form and its page.
    name_form: type
    name_template: str
    # Adding it in account settings' 登入方式 (views/sign_in_methods.py).
    taken: str
    added: str
    not_added: str  # no wording in either mockup (drafts)
    # 確認本人 with it (views/confirm_identity.py): another account's code came back; the trip
    # was cancelled, refused or the provider down (no wording in either mockup, drafts); removed;
    # its button.
    not_yours: str
    not_confirmed: str
    removed: str
    confirm_button: str


WORDS = {
    "google": ProviderWords(
        cancelled="沒有完成 Google 登入。可以再試一次，或用其他方式登入。",
        unavailable="Google 暫時沒有回應，請稍後再試，或用其他方式登入。",
        name_expired="等太久了，請再按一次「使用 Google 帳戶登入」。",
        not_answering_log="Google token exchange failed",
        rejected_log="Google callback rejected",
        name_form=GoogleNameForm,
        name_template="screening/google_name.html",
        taken="這個 Google 帳號已經用在另一個聽伴帳號，所以沒有新增。",
        added="已新增 Google 登入。下次可以直接用 Google 登入。",
        not_added="沒有完成新增 Google 登入，請再試一次。",
        not_yours="這不是您帳號上的 Google。請改用註冊時用的那個 Google 帳戶。",
        not_confirmed="沒有完成 Google 確認，請再試一次。",
        removed="已移除 Google 登入。",
        confirm_button="使用 Google 帳戶確認",
    ),
    "line": ProviderWords(
        cancelled="沒有完成 LINE 登入，可以再試一次，或用其他方式登入。",
        unavailable="LINE 暫時沒有回應，請稍後再試，或用其他方式登入。",
        # No wording in the #539 mockup: Google's, with the LINE button's words (W1).
        name_expired="等太久了，請再按一次「使用 LINE 帳號登入」。",
        # Also when LINE's verify endpoint is down.
        not_answering_log="LINE token exchange failed",
        rejected_log="LINE callback rejected",
        # LINE gives no email, so its form asks for one (#506 acceptance 5).
        name_form=LineNameForm,
        name_template="screening/line_name.html",
        taken="這個 LINE 帳號已經用在另一個帳號。",
        added="已新增 LINE 登入。下次可以直接用 LINE 登入。",
        not_added="沒有完成新增 LINE 登入，請再試一次。",
        not_yours="這不是您帳號上的 LINE。請用註冊時那支手機上的 LINE 再試一次。",
        not_confirmed="沒有完成 LINE 確認，請再試一次。",
        removed="已移除 LINE 登入。",
        confirm_button="使用 LINE 帳號確認",
    ),
}
