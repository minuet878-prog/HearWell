from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.forms import BaseFormSet, formset_factory
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from screening.models import (
    AidAndSubsidy,
    AidEar,
    AidLevel,
    Answer,
    ApprovedEars,
    Certificate,
    Question,
    Submission,
    Subsidy,
    User,
    shared_days,
)
from screening.questionnaires.definition import (
    HEARING_AID,
    LIFE_IMPACT,
    LISTENING,
    TINNITUS,
    UNSURE,
)

ROC_OFFSET = 1911  # 民國 year + 1911 = Western year

# Issue #151: the site's own words for the rules AUTH_PASSWORD_VALIDATORS checks, in the same
# order; the validators still decide, and their error messages are unchanged.
PASSWORD_RULES = ("至少 8 個字", "不要全部是數字", "不要跟您的使用者名稱太像", "不要用太常見的密碼")
# The site's own words in place of Django's username help; its validator and 150 limit stay.
USERNAME_HELP = "登入時要輸入的名字，可以用中文、英文或數字，不要有空格。不用寫真實姓名。"


def latest_roc_birth_year():
    """The latest 民國 birth year registering accepts: someone who turns 18 this year."""
    return date.today().year - 18 - ROC_OFFSET


class NoLabelSuffix:
    """Field names without Django's colon after them, the same on every form (#354)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)


class RegisterForm(NoLabelSuffix, UserCreationForm):
    email = forms.EmailField(label="電子郵件", help_text="忘記密碼時，用這個信箱確認是您本人。")
    roc_birth_year = forms.CharField(
        label="出生年（選填）",
        required=False,
        help_text="選填。填了之後會直接推薦適合您年齡的問卷，不用再問一次。不會公開。",
        widget=forms.TextInput(attrs={"inputmode": "numeric", "maxlength": 3}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        if not self.is_bound:
            self.fields["username"].widget.attrs.pop("autofocus", None)
        self.fields["username"].help_text = USERNAME_HELP
        self.fields["password1"].help_text = format_html(
            "設定密碼時，請您注意：<ul>{}</ul>",
            format_html_join("", "<li>{}</li>", ((rule,) for rule in PASSWORD_RULES)),
        )
        self.fields["password2"].help_text = "請再輸入一次同樣的密碼。"
        # #332 (spec #326 D6): the page's green tick checks against the same latest year.
        self.fields["roc_birth_year"].widget.attrs["data-max"] = latest_roc_birth_year()

    def clean_roc_birth_year(self):
        value = self.cleaned_data["roc_birth_year"]
        if not value:
            return None
        max_roc = latest_roc_birth_year()
        # isdecimal() accepts exactly what int() accepts; isdigit() also lets through "²".
        if not value.isdecimal() or not 1 <= int(value) <= max_roc:
            raise forms.ValidationError(f"請輸入民國 1 到 {max_roc} 年之間的數字")
        return int(value)

    def save(self, commit=True):
        user = super().save(commit=False)
        roc = self.cleaned_data["roc_birth_year"]
        user.birth_year = None if roc is None else roc + ROC_OFFSET
        if commit:
            user.save()
        return user


def answer_choices(question):
    return question.questionnaire.definition.choices(question.question_number)


def offers_not_applicable(question):
    """Whether the question lists 「不適用」, whose answer is an empty score."""
    return "na" in dict(answer_choices(question))


class DeleteAccountForm(NoLabelSuffix, forms.Form):
    # strip=False like Django's login and register forms: spaces are part of a password.
    password = forms.CharField(strip=False, error_messages={"required": "請輸入密碼"})

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("密碼不正確")
        return password


class AnswerForm(NoLabelSuffix, forms.Form):
    score = forms.TypedChoiceField(
        coerce=int,
        widget=forms.RadioSelect(attrs={"class": "choice-group"}),
        error_messages={"required": "這一題還沒有回答"},
    )
    question_id = forms.ModelChoiceField(
        queryset=Question.objects.all(), widget=forms.HiddenInput()
    )

    def __init__(self, *args, choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["score"].choices = choices
        self.fields["score"].coerce = lambda value: None if value == "na" else int(value)


class HearingAidForm(NoLabelSuffix, forms.Form):
    wearing_hearing_aid = forms.TypedChoiceField(
        choices=((True, "有戴"), (False, "沒戴")),
        coerce=lambda value: value == "True",
        widget=forms.RadioSelect(attrs={"class": "choice-group"}),
    )

    def __init__(self, *args, message, **kwargs):
        # message: the questionnaire's own (Definition.wearing_error), asked as its question is.
        super().__init__(*args, **kwargs)
        self.fields["wearing_hearing_aid"].error_messages.update(
            {"required": message, "invalid_choice": message}
        )


class BaseAnswerFormSet(BaseFormSet):
    def __init__(
        self,
        *args,
        questions,
        **kwargs,
    ):
        self.questions = questions
        # A questionnaire has a fixed set of questions, so no form may be left blank. Django lets
        # "extra" forms (index >= INITIAL_FORMS) pass empty; a tampered TOTAL_FORMS then reached
        # clean() with no question_id and returned 500.
        kwargs["form_kwargs"] = {**kwargs.get("form_kwargs", {}), "empty_permitted": False}
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        # Forms past the real questions (tampered TOTAL_FORMS) get no choices, so they fail.
        if index is not None and index < len(self.questions):
            kwargs["choices"] = answer_choices(self.questions[index])
        return kwargs

    def clean(self):
        if any(self.errors):
            raise forms.ValidationError("表單資料有誤，請重新確認每一題的作答")
        expected = [question.id for question in self.questions]
        submitted = []
        for form in self:
            submitted.append(form.cleaned_data["question_id"].id)
        if len(submitted) != len(set(submitted)):
            raise forms.ValidationError("重複題目")
        elif set(submitted) != set(expected):
            raise forms.ValidationError("有題目沒有作答")

    def save(self, user, questionnaire, **extra):
        # All or nothing: no submission without its answers.
        with transaction.atomic():
            submission = Submission.objects.create(user=user, questionnaire=questionnaire, **extra)
            Answer.objects.bulk_create(
                Answer(
                    submission=submission,
                    question=form.cleaned_data["question_id"],
                    score=form.cleaned_data["score"],
                )
                for form in self
            )
        return submission


AnswerFormSet = formset_factory(AnswerForm, formset=BaseAnswerFormSet, extra=0)


class AgeGroupForm(NoLabelSuffix, forms.Form):
    # The answers' values, also used when the birth year already tells the age (#152).
    ADULT, OLDER = "adult", "older"
    age_group = forms.ChoiceField(
        label="您目前的實際年齡？",
        choices=((ADULT, "18–64 歲"), (OLDER, "65 歲以上")),
        widget=forms.RadioSelect(attrs={"class": "choice-group"}),
        error_messages={"required": "請選擇您的年齡區間"},
    )


class ConcernForm(NoLabelSuffix, forms.Form):
    # The recommendation wizard's first question (ADR 0030).
    concern = forms.ChoiceField(
        label="您最想了解什麼？",
        choices=(
            (LIFE_IMPACT, "聽不清楚對生活、心情的影響"),
            (TINNITUS, "耳鳴的困擾"),
            (LISTENING, "吵雜地方、多人說話聽不懂"),
            (HEARING_AID, "助聽器戴得好不好"),
            (UNSURE, "不確定"),
        ),
        widget=forms.RadioSelect(attrs={"class": "choice-group"}),
        error_messages={"required": "請選擇您最想了解的事"},
    )


class ComparisonRecordField(forms.ModelChoiceField):
    # The Taipei dates this questionnaire's comparable records share; set by the form.
    shared_days = frozenset()

    def label_from_instance(self, obj):
        result = obj.questionnaire.definition.comparison.record_result(obj)
        when = timezone.localtime(obj.created_at)
        shown = when.strftime("%Y/%m/%d %H:%M" if when.date() in self.shared_days else "%Y/%m/%d")
        return f"{shown}・{result}"


class HhiComparisonForm(NoLabelSuffix, forms.Form):
    # Radio cards (#190). Nothing is saved until the user presses save (ADR 0003); with no saved
    # pair, a side with only one record has it chosen, two or more wait for the user (F2).
    unaided = ComparisonRecordField(
        label="沒戴助聽器時",
        queryset=Submission.objects.none(),
        widget=forms.RadioSelect(attrs={"class": "choice-group choice-stack"}),
    )
    aided = ComparisonRecordField(
        label="戴助聽器時",
        queryset=Submission.objects.none(),
        widget=forms.RadioSelect(attrs={"class": "choice-group choice-stack"}),
    )

    def __init__(self, *args, user, questionnaire, **kwargs):
        super().__init__(*args, **kwargs)
        records = user.submissions.filter(questionnaire=questionnaire).select_related(
            "questionnaire"
        )
        records = questionnaire.definition.comparison.records(records)
        days = shared_days(
            records.filter(wearing_hearing_aid__isnull=False).values_list("created_at", flat=True)
        )
        choose_lone_records = not self.initial  # no saved pair
        for name, wearing in (("unaided", False), ("aided", True)):
            self.fields[name].queryset = records.filter(wearing_hearing_aid=wearing)
            self.fields[name].shared_days = days
            if choose_lone_records:
                # Two are enough to tell a lone record; chosen through initial, as a saved pair is.
                first_two = list(self.fields[name].queryset.values_list("pk", flat=True)[:2])
                if len(first_two) == 1:
                    self.initial[name] = first_two[0]


class CertificateForm(NoLabelSuffix, forms.ModelForm):
    # 身障鑑定與鑑定醫院's question (spec #291 Q2): one press of an answer sends it.
    certificate = forms.ChoiceField(
        label="您有聽覺機能的身心障礙證明嗎？",
        help_text="第二類 b230、s260，或舊制 02",
        choices=Certificate.choices,
    )

    class Meta:
        model = AidAndSubsidy
        fields = ("certificate",)


def _done_or_not_yet(label, done):
    # #294: 完成了 / 收到了, or 還沒, kept as True or False.
    return forms.TypedChoiceField(
        label=label, choices=((True, done), (False, "還沒")), coerce=lambda value: value == "True"
    )


class Form9Form(NoLabelSuffix, forms.ModelForm):
    form_9_done = _done_or_not_yet("九號表完成了嗎？", "完成了")

    class Meta:
        model = AidAndSubsidy
        fields = ("form_9_done",)


class NoticeForm(NoLabelSuffix, forms.ModelForm):
    notice_received = _done_or_not_yet("收到核定公文了嗎？", "收到了")

    class Meta:
        model = AidAndSubsidy
        fields = ("notice_received",)


class ApprovedEarsForm(NoLabelSuffix, forms.ModelForm):
    approved_ears = forms.ChoiceField(label="核定的是單耳還是雙耳？", choices=ApprovedEars.choices)

    class Meta:
        model = AidAndSubsidy
        fields = ("approved_ears",)


class ApprovedLevelForm(NoLabelSuffix, forms.ModelForm):
    level = forms.ChoiceField(label="補助的等級是？", choices=AidLevel.choices)

    class Meta:
        model = AidAndSubsidy
        fields = ("level",)


def _radios(label, choices, **kwargs):
    # Optional: a question left unchosen keeps what was there (#295 only writes what is given).
    return forms.ChoiceField(
        label=label,
        choices=choices,
        required=False,
        widget=forms.RadioSelect(attrs={"class": "choice-group"}),
        **kwargs,
    )


class FittingForm(NoLabelSuffix, forms.ModelForm):
    # 配戴之後's questions (#295, spec #291 Q6): the date, then only what is not known yet. The
    # notice's 單耳 asks which ear, its 雙耳 none; without the notice, the ear, the subsidy and
    # its level. Saved with one button; the date picker is the one recording an audiogram uses.
    fitted_on = forms.DateField(
        label="這副助聽器哪一天開始戴？",
        help_text="可以看購買收據或保固書上的日期",
        widget=forms.DateInput(
            format="%Y-%m-%d", attrs={"type": "date", "class": "form-control form-control-lg"}
        ),
    )
    ear = _radios("戴哪一耳？", AidEar.choices)
    subsidy = _radios("有沒有用身障補助買？", Subsidy.choices)
    # fitting-level.js shows it only with 用身障補助; without JavaScript it stays (#287).
    level = _radios("補助的等級是？", AidLevel.choices, help_text="選了用身障補助才需要填")
    save_label = "儲存"
    # 修改 offers to clear the pair (spec #291 acceptance 18) instead of the date field's own.
    NOT_FITTED = "not_fitted"

    class Meta:
        model = AidAndSubsidy
        fields = ("fitted_on", "ear", "subsidy", "level")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fitted_on"].widget.attrs["max"] = timezone.localdate().isoformat()
        self.answered = self.instance.fitted_on is not None
        self.not_fitted = self.NOT_FITTED in self.data
        aid = self.instance
        if aid.notice_received:
            del self.fields["subsidy"], self.fields["level"]  # the notice's answers stand
            if aid.approved_ears == ApprovedEars.ONE:
                self.fields["ear"].choices = AidEar.choices[:2]  # 左耳 or 右耳
            elif aid.approved_ears == ApprovedEars.BOTH:
                del self.fields["ear"]
        if self.not_fitted:
            self.fields["fitted_on"].required = False

    def clean_fitted_on(self):
        fitted_on = self.cleaned_data["fitted_on"]
        if fitted_on and fitted_on > timezone.localdate():
            raise forms.ValidationError("開始配戴日期不能是未來")
        return fitted_on

    def clean(self):
        # The instance is set here, as construct_instance leaves an unsent radio's field as it
        # was; the model's clean then drops a level without 用身障補助.
        aid = self.instance
        if self.not_fitted:
            # 還沒開始戴: what 配戴之後 asked goes, and form 25, which the next pair is done
            # again; the notice's answers stay.
            aid.fitted_on, aid.ear, aid.subsidy, aid.form_25_done = None, "", "", None
            return {}
        if aid.notice_received and aid.approved_ears == ApprovedEars.BOTH:
            aid.ear = AidEar.BOTH
        # Spec #291 Q16: without the notice the subsidy must be answered. Checked here, not
        # as a required radio, so 還沒開始戴 still goes through on an older record without it.
        if "subsidy" in self.fields and not self.cleaned_data.get("subsidy"):
            self.add_error("subsidy", "請選擇有沒有用身障補助")
        return super().clean()


class Form25Form(NoLabelSuffix, forms.ModelForm):
    form_25_done = _done_or_not_yet("二十五號表完成了嗎？", "完成了")  # #296

    class Meta:
        model = AidAndSubsidy
        fields = ("form_25_done",)


# The stops asked on the 選配路線 and at the foot of their chapters (#293), by slug: each
# stop's questions in the order they are asked, one at a time (#294: the notice's three).
STOP_QUESTIONS = {
    "assessment": (CertificateForm,),
    "form-9": (Form9Form,),
    "notice": (NoticeForm, ApprovedEarsForm, ApprovedLevelForm),
    "after-fitting": (FittingForm,),
    "form-25": (Form25Form,),
}
