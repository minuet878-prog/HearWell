"""引言 (ADR 0076, spec #741 story 52): the line the bird says above each page's title.

The one place for every page's lead. Keyed by the page's URL name; a page with more than one
state (a link that no longer works, a form already sent) has a key of its own for each. The owner
reviewed every line on 2026-11-21; a new or changed lead goes to the owner before it goes live.
A lead with {name} takes the account's name.
"""

LEADS = {
    # 首頁 has none: its bubble is one line, as the canvas (spec #741's 實作中本人補充).
    # 問卷
    "questionnaire_list": "不確定做哪一份？我可以幫您選。",
    # The wizard and the answer page have no lead (the owner's 2026-11-27 walkthrough).
    "questionnaire_recommended": "照您的回答，這一份最適合。",
    # A result page's bubble is this one line, its title, with no lead (the owner, 2026-11-27).
    "result": "辛苦了，看看結果",
    # The same result opened again later (上次結果, 我的紀錄, a reload): views.common.JUST_SAVED.
    "result_reopened": "這是您這一次的結果",
    "guest_save": "這次的結果還在這支手機上。",
    "guest_saved": "存好了。",
    "hhi_comparison": "戴上助聽器，差多少？",
    # 紀錄
    "my_hearing": "這裡是您每一次的紀錄。",
    "audiogram_new": "照檢查報告上的數字填就好。",
    "audiogram_import": "用 iPhone 做過聽力測試嗎？",
    "audiogram_import_preview": "存起來之前，先看一眼。",
    "audiogram_detail": "這是您記下的聽力圖。",
    "audiogram_compare": "看看前後有沒有變化。",
    "audiogram_delete": "刪除之前，請再確認一次。",
    "audiogram_speech_banana": "看看哪些說話的聲音聽得到。",
    "health_report": "可以印出來，帶去看診。",
    "share_report": "讓家人也知道您的聽力狀況。",
    "shared_cover": "您好，這是聽伴。",
    "shared_report": "這是家人的聽力報告。",
    "share_invalid": "可以請家人再傳一次新的連結。",
    # 了解
    "learn": "想多了解一點嗎？",
    "guide": "一步一步來，不用急。",
    "guide_chapter": "慢慢看，有問題可以問聽力師。",
    # #775: a draft until the owner has reviewed it.
    "guide_subsidy": "回答幾題，一起算算看。",
    "family_guide": "謝謝您關心家人的聽力。",
    "family_talk": "換個方式說，他會聽得更清楚。",
    "family_reluctant": "長輩不想去，是很常見的事。",
    "family_hearing_aids": "陪他一起認識助聽器。",
    "family_visits": "陪他去，事情會順利很多。",
    "family_subsidy_check": "看看他可以申請哪些補助。",
    "family_deadlines": "算一算，哪天之前要辦好。",
    "family_question": "很多家人都問過這一題。",
    "hearing_loss_simulator": "聽聽看，聽力不好的人聽到什麼。",
    "qa_home": "有問題，可以問我。",
    "qa_topic": "這是這個主題常見的問題。",
    "qa_answer": "這一題的回答在這裡。",
    "qa_results": "這是我找到的回答。",
    "about": "想知道是誰做的嗎？",
    "privacy": "您的資料怎麼保管，都寫在這裡。",
    "feedback": "有什麼想法，都可以告訴我們。",
    "feedback_sent": "收到了。",
    "add_to_home": "放在主畫面，下次一點就打開。",
    # 帳號
    "login": "歡迎回來。",
    "register": "建立帳號，篩檢結果會幫您存起來。",
    "consent": "使用之前，請先看看這些說明。",
    "account_settings": "{name}，這裡可以管理您的帳號。",
    "delete_account": "刪除之前，請先看清楚。",
    "confirm_identity": "為了保護您的資料。",
    "add_email": "留個 email，忘記密碼時才找得回帳號。",
    "email_confirm": "還差一步。",
    "email_confirmed": "謝謝您。",
    "email_confirm_invalid": "這個連結可能過期了。",
    "password_reset": "別擔心，寄一封信幫您重設。",
    "password_reset_sent": "請到信箱看看。",
    "password_reset_confirm": "最後一步了。",
    "password_reset_invalid": "這個連結可能過期了。",
    "sign_in_name": "快好了。",
    "google_same_email": "看起來您之前來過。",
    "reminder_cancel": "不想再收到提醒信嗎？",
    "reminder_cancelled": "好的。",
    "reminder_invalid": "這個連結可能過期了。",
    # 錯誤頁
    "not_found": "這一頁好像不見了。",
    "server_error": "抱歉，請稍後再試一次。",
}


def page_lead(key, name=""):
    """The lead for this key; a missing key fails loudly rather than show an empty bubble."""
    return LEADS[key].format(name=name)
