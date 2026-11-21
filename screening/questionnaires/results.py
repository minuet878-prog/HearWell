"""Result types (GLOSSARY 結果類型, spec #385): how one record's result is worked out and shown.

A definition's `result` is one of these classes; `submission.result` is it bound to that record.
Callers ask the record's result instead of checking which type it is (ADR 0036).

Scores come from the record's one scoring path (`with_scores()` or `_calculate_scores`), item data
from the answers the caller prefetched (a subscale record alone loads its own). A graded result
from_answers() (a guest's, #494) is bound to an unsaved record instead: its scores worked out from
its answers in Python (scores_from_answers), with no query and no account. The imports inside
methods break an import cycle: the definitions import this module, and scoring and the models
import the definitions.
"""

import math
from decimal import ROUND_HALF_UP, Decimal
from functools import cached_property

from django.db.models import Prefetch, prefetch_related_objects
from django.utils import timezone


class Result:
    # Templates call what they can call: definition.result must stay the class there.
    do_not_call_in_templates = True

    # What this type does not have is None, never 0.
    total = None
    subscores = None  # {"emotional": int, "social": int}
    level = None  # classify()'s {"text", "level", "color"}
    average = None  # Decimal to one place
    unavailable_reason = None  # why there is no average (ADR 0001)
    satisfaction = None  # the definition's score(): overall, subscales, not_applicable
    norm_group = None  # the norm group's name
    norm_summary = None  # the record against its norm group, for the report
    not_applicable_choice = None  # the download's choice for an answer without a score
    # The result page's 與上次比較 (#461): {"label", "text", "level_change"}; graded only.
    since_last = None

    # The record's row of 我的紀錄 (#409) and its result page; page_context() is the page's data
    # of this type, the view adding what every page has.
    row_template = None
    # The questionnaire catalogue card's words after 「上次」 and its date (#649), from the same
    # line as its row; None: the date alone.
    card_template = None
    page_template = None
    page_shows_wearing = True  # the result page's header says how the hearing aids were worn

    def __init__(self, submission, answers=None):
        self.submission = submission
        # A result from_answers(): its answers not saved, in item order. None reads the record's.
        self.unsaved_answers = answers

    @property
    def is_guest(self):
        # A guest's result (from_answers(), spec #492): no saved record, so no account behind it.
        return self.submission.pk is None

    @property
    def lowest_answers(self):  # up to 3 answers with a score, lowest first
        return []

    def page_context(self):
        return {}

    def export(self):
        # 「下載我的資料」's fields of this record after its answers, in the file's order.
        subscores = self.subscores or {"emotional": None, "social": None}
        return {
            "total_score": self.total,
            "emotional_score": subscores["emotional"],
            "social_score": subscores["social"],
            "level": self.level["text"] if self.level else None,
            "norm_group": self.norm_group,
        }

    def _answers(self):  # the result page's answers, in item order
        if self.unsaved_answers is not None:
            return self.unsaved_answers
        return self.submission.answers.select_related("question__questionnaire").order_by(
            "question__question_number"
        )


class GradedResult(Result):
    """分級: the total graded by thresholds, with advice (HHIE-S, HHIA-S, THI)."""

    row_template = "screening/record_rows/graded.html"
    card_template = "screening/summaries/level.html"
    page_template = "screening/result.html"

    @classmethod
    def from_answers(cls, questionnaire, answers, wearing_hearing_aid):
        """The result of answers not saved, worked out without a query and without an account
        (a guest's, #494; spec #492): bound to an unsaved record, so the result page's template
        draws it as it draws a saved one's. answers: (question, score) pairs of this
        questionnaire, the questions with their questionnaire loaded (questionnaire.questions)."""
        from screening.models import Answer, Submission, scores_from_answers

        submission = Submission(
            questionnaire=questionnaire, wearing_hearing_aid=wearing_hearing_aid
        )
        unsaved = sorted(
            (Answer(question=question, score=score) for question, score in answers),
            key=lambda answer: answer.question.question_number,
        )
        submission._scores_cache = scores_from_answers(unsaved)
        submission.result = cls(submission, unsaved)
        return submission.result

    @property
    def total(self):
        return self.submission.total_answer_score

    @property
    def subscores(self):
        # Only records with emotional or social items (#386); THI has none.
        scores = self.submission._calculate_scores()
        if scores["subscore_answer_count"] == 0:
            return None
        return {"emotional": scores["score_emotional"], "social": scores["score_social"]}

    @cached_property
    def level(self):
        from screening.scoring import classify

        return classify(self.total, self.submission.questionnaire.code)

    @cached_property
    def since_last(self):
        # Against this questionnaire's record just before this one worn the same way, even when
        # a newer one exists (spec #453 acceptance 26; the owner on #461: worn against not worn
        # is the wearing comparison's). The same rule as 我的紀錄's previous_same_wearing: no
        # hearing aid status, no comparison. None also for the first, or when either cannot be
        # graded.
        from screening.models import Submission
        from screening.scoring import (
            UNKNOWN,
            change_label_text,
            level_change_text,
            result_since_last_text,
        )

        submission = self.submission
        # A guest's result has no account, so nothing to compare with (#494).
        if self.is_guest or submission.wearing_hearing_aid is None:
            return None
        previous = (
            Submission.objects.filter(
                user_id=submission.user_id,
                questionnaire_id=submission.questionnaire_id,
                wearing_hearing_aid=submission.wearing_hearing_aid,
            )
            .earlier_than(submission)
            .select_related("questionnaire")
            .with_scores()
            .first()
        )
        if previous is None:
            return None
        level, previous_level = self.level, previous.result.level
        if UNKNOWN["level"] in (level["level"], previous_level["level"]):
            return None
        day = timezone.localdate(previous.created_at)
        previous_total = previous.result.total
        changed = level["level"] != previous_level["level"]
        difference = self.total - previous_total
        ceiling = self.submission.questionnaire.definition.thresholds[-1][0]
        return {
            "label": change_label_text(difference),
            "text": result_since_last_text(day, previous_total, difference),
            "level_change": (
                level_change_text(previous_level["text"], level["text"]) if changed else None
            ),
            # #750 (canvas ProResult): the two bars, each total's share of the full score.
            "previous_total": previous_total,
            "previous_width": previous_total / ceiling * 100,
            "width": self.total / ceiling * 100,
        }

    def page_context(self):
        from screening.care_journey import WHERE_TO_TEST
        from screening.models import Questionnaire
        from screening.questionnaires import hhia_s, hhie_s, ssq12_tw
        from screening.scoring import SCORE_SUM_TEXT, get_advice, max_score

        submission = self.submission
        definition = submission.questionnaire.definition
        code = submission.questionnaire.code
        answers = self._answers()
        level = self.level["level"]
        next_steps = definition.next_steps.get(level, ())
        # The 2026-11-14 walkthrough (mockup 3A): a guest sees the step that says to have the
        # hearing checked outside the fold, in place of the 照顧旅程 card's advice. It is the
        # reviewed step marked HEARING_CHECK; the fold then leaves it out.
        advice_step = (
            next((step for step in next_steps if step.get("hearing_check")), None)
            if self.is_guest
            else None
        )
        # The page reads its total, subscores and level from submission.result itself.
        return {
            "answers": answers,
            "max_score": max_score(code),
            "gauge": semicircle_gauge(definition, self.total, level),
            "next_steps": next_steps,
            "advice_step": advice_step,
            "where_to_test": WHERE_TO_TEST,
            # Under 這個分數怎麼算 (#750): every reviewed step; a guest's first and the one it
            # sees outside stay where they are.
            "fold_steps": (
                [step for step in next_steps[1:] if step is not advice_step]
                if self.is_guest
                else list(next_steps)
            ),
            "score_sum_text": SCORE_SUM_TEXT,
            "level_ranges": level_ranges(definition),
            # A guest's save card (spec #492); "" for a level it has no sentence for.
            "save_reason": definition.save_reasons.get(level, ""),
            "advice": get_advice(level, code),
            "support_message": definition.support(
                {answer.question.question_number: answer.score for answer in answers}
            ),
            "optional_ssq12": (
                Questionnaire.objects.filter(code=ssq12_tw.CODE).first()
                # Only with an account: SSQ12-TW needs one (spec #492).
                if not self.is_guest
                and code in (hhie_s.CODE, hhia_s.CODE)
                and submission.wearing_hearing_aid is False
                else None
            ),
        }


def level_ranges(definition):
    # 這個分數怎麼算 (#750): each level's lowest and highest total, by its full name.
    ranges = []
    low = 0
    for upper, text, _level in definition.thresholds:
        ranges.append({"low": low, "high": upper, "text": text})
        low = upper + 1
    return ranges


# The semicircle gauge's drawing (semicircle_gauge.html, canvas ProResult): its centre and radius
# in the SVG's own units, and the gap left at each side of a level's border, as a share of the arc.
GAUGE_CENTRE = (159, 150)
GAUGE_RADIUS = 124
GAUGE_GAP = 0.012


def _gauge_point(share):
    # The point share of the way along the arc, from its left end over the top to its right end.
    angle = math.pi * (1 - share)
    centre_x, centre_y = GAUGE_CENTRE
    x = centre_x + GAUGE_RADIUS * math.cos(angle)
    y = centre_y - GAUGE_RADIUS * math.sin(angle)
    return round(x, 1), round(y, 1)


def semicircle_gauge(definition, score, level):
    """#750 (canvas ProResult): one arc for each level, the score's level drawn thick, and a knob
    where the score is. "無法判讀" (no thresholds, or an out-of-range score) draws none."""
    thresholds = definition.thresholds
    if level == "unknown" or not thresholds:
        return None
    ceiling = thresholds[-1][0]
    arcs = []
    start = 0
    for upper, _text, arc_level in thresholds:
        begin = _gauge_point(start / ceiling + (GAUGE_GAP if start else 0))
        end = _gauge_point(upper / ceiling - (GAUGE_GAP if upper < ceiling else 0))
        arcs.append(
            {
                "path": f"M{begin[0]} {begin[1]}A{GAUGE_RADIUS} {GAUGE_RADIUS} 0 0 1 "
                f"{end[0]} {end[1]}",
                "color": definition.color(arc_level),
                "shade": definition.shade(arc_level),
                "current": arc_level == level,
            }
        )
        start = upper
    knob = _gauge_point(max(0, min(1, score / ceiling)))
    return {"arcs": arcs, "knob": knob, "ceiling": ceiling}


class AverageResult(Result):
    """平均: the average of the items, no grade (SSQ12-TW)."""

    row_template = "screening/record_rows/average.html"
    card_template = "screening/summaries/average.html"
    page_template = "screening/ssq12_result.html"
    not_applicable_choice = "不適用"

    @cached_property
    def average(self):
        # Only with all 12 items answered with a number (ADR 0001).
        scores = self.submission._calculate_scores()
        if scores["numeric_count"] != 12 or scores["answer_count"] != 12:
            return None
        return (Decimal(scores["score_total"]) / 12).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )

    @property
    def unavailable_reason(self):
        if self.average is not None:
            return None
        if self.submission._calculate_scores()["numeric_count"] == 0:
            return "未計算：沒有可用數值回答"
        return "未計算：包含不適用題目"

    @cached_property
    def lowest_answers(self):
        # 「分數最低的 n 題」 (ticket #189): ties by item number; 不適用 is left out, and there is
        # no threshold. Only the result page asks, so it may query.
        return list(
            self.submission.answers.filter(score__isnull=False)
            .select_related("question")
            .order_by("score", "question__question_number")[:3]
        )

    def page_context(self):
        return {"answers": self._answers()}

    def export(self):
        return super().export() | {
            "average_score": str(self.average) if self.average is not None else None,
            "average_unavailable_reason": self.unavailable_reason,
        }


class NormResult(Result):
    """常模比對: each item against the norms, no total (IOI-HA)."""

    row_template = "screening/record_rows/norm.html"
    page_template = "screening/result_ioi_ha.html"
    page_shows_wearing = False  # not asked: IOI-HA is answered about the hearing aids worn

    @property
    def norm_group(self):
        # Fixed when it was submitted; "" (none) on records from before norm groups.
        return self.submission.get_norm_group_display() or None

    @cached_property
    def norm_summary(self):
        # Only one record's at a time (the home page's last result, the report), so it may query.
        return ioi_ha_summary(self.submission)

    def page_context(self):
        # No total, level or advice: read item by item against the fixed norm group.
        from screening.questionnaires.ioi_ha import SCALE_ENDS
        from screening.scoring import NORM_VERSUS_TEXT

        items, grouped = _ioi_ha_items(self.submission, self._answers(), NORM_VERSUS_TEXT)
        # Items below the norm come first and open; the rest are folded under 「其他 n 項」 (#187).
        below = [item for item in items if item["comparison_code"] == "below"]
        return {
            "items": items,
            "grouped": grouped,
            "below": below,
            "below_text": NORM_VERSUS_TEXT["below"],
            "others": [item for item in items if item not in below],
            "scale_ends": SCALE_ENDS,
        }


def _ioi_ha_items(submission, answers, texts):
    # The only place IOI-HA answers meet the norms; the result page and the report both use it,
    # each with its own words for the comparison (texts: NORM_VERSUS_TEXT or NORM_COMPARISON_TEXT).
    from screening.models import NormGroup
    from screening.questionnaires.ioi_ha import ITEM_CHOICES as IOI_HA_CHOICES
    from screening.scoring import (
        IOI_HA_BELOW_NORM_NOTES,
        IOI_HA_ITEM_NAMES,
        IOI_HA_NORMS,
        compare_to_norm,
    )

    grouped = submission.norm_group != NormGroup.UNGROUPED
    items = []
    for answer in answers:
        number = answer.question.question_number
        comparison = (
            compare_to_norm(submission.norm_group, number, answer.score) if grouped else None
        )
        norm = IOI_HA_NORMS[submission.norm_group][number] if grouped else None
        items.append(
            {
                "name": IOI_HA_ITEM_NAMES[number],
                "text": answer.question.question_text,
                "label": IOI_HA_CHOICES[number][answer.score - 1],
                "comparison_code": comparison,
                "comparison": texts.get(comparison),
                "note": IOI_HA_BELOW_NORM_NOTES[number] if comparison == "below" else None,
                # The result page's 5-cell scale, scores 1-5: the norm cells and the answer.
                "cells": [
                    {
                        "band": norm is not None and norm[0] <= score <= norm[1],
                        "mine": score == answer.score,
                    }
                    for score in range(1, 6)
                ],
            }
        )
    return items, grouped


def ioi_ha_summary(submission):
    # One IOI-HA record against the norms, for the report and the home page's last result.
    from screening.scoring import NORM_COMPARISON_TEXT

    answers = submission.answers.select_related("question").order_by("question__question_number")
    items, grouped = _ioi_ha_items(submission, answers, NORM_COMPARISON_TEXT)
    return {
        "submission": submission,
        "items": items,
        "grouped": grouped,
        "below": sum(item["comparison_code"] == "below" for item in items),
        "above": sum(item["comparison_code"] == "above" for item in items),
    }


class SubscaleResult(Result):
    """分量表: the overall and subscale averages (SADL)."""

    row_template = "screening/record_rows/subscale.html"
    card_template = "screening/summaries/subscale.html"
    page_template = "screening/sadl_result.html"
    page_shows_wearing = False  # not asked: always worn (always_aided)
    not_applicable_choice = "不適用"

    @cached_property
    def satisfaction(self):
        # The only scoring path for subscale questionnaires. A list prefetches the answers with
        # their questions and scores every record from one query; one record alone (the home
        # page's last result) loads them here in one query, not one per answer's question (#407).
        self._load_answers()
        answers = self.submission.answers.all()
        definition = self.submission.questionnaire.definition
        return definition.score({a.question.question_number: a.score for a in answers})

    def _load_answers(self):
        # The answers with their questions, unless the caller already prefetched the answers:
        # then they are used as they are, so a caller prefetches them with their questions.
        from screening.models import Answer

        prefetch_related_objects(
            [self.submission],
            Prefetch("answers", queryset=Answer.objects.select_related("question")),
        )

    def export(self):
        satisfaction = self.satisfaction
        return super().export() | {
            "overall_score": str(satisfaction["overall"]),
            "subscale_scores": {s["name"]: str(s["score"]) for s in satisfaction["subscales"]},
        }

    def page_context(self):
        # The page reads satisfaction and each answer from the record: one query for both.
        self._load_answers()
        return {}
