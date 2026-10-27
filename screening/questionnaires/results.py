"""Result types (GLOSSARY 結果類型, spec #385): how one record's result is worked out and shown.

A definition's `result` is one of these classes; `submission.result` is it bound to that record.
Callers ask the record's result instead of checking which type it is (ADR 0036).

Scores come from the record's one scoring path (`with_scores()` or `_calculate_scores`), item data
from the answers the caller prefetched (a subscale record alone loads its own). The imports inside
methods break an import cycle: the definitions import this module, and scoring and the models
import the definitions.
"""

from decimal import ROUND_HALF_UP, Decimal
from functools import cached_property

from django.db.models import Prefetch, prefetch_related_objects


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
    norm_summary = None  # the record against its norm group, for the home page and the report
    not_applicable_choice = None  # the download's choice for an answer without a score

    # The record's summary (plain text: the home page's last result, in a block, and the report;
    # None: none), its row of 我的紀錄 (#409) and its result page; page_context() is the page's data
    # of this type, the view adding what every page has.
    summary_template = None
    row_template = None
    page_template = None
    page_shows_wearing = True  # the result page's header says how the hearing aids were worn

    def __init__(self, submission):
        self.submission = submission

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
        return self.submission.answers.select_related("question__questionnaire").order_by(
            "question__question_number"
        )


class GradedResult(Result):
    """分級: the total graded by thresholds, with advice (HHIE-S, HHIA-S, THI)."""

    row_template = "screening/record_rows/graded.html"
    page_template = "screening/result.html"

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

    def page_context(self):
        from screening.models import Questionnaire
        from screening.questionnaires import hhia_s, hhie_s, ssq12_tw
        from screening.scoring import UNKNOWN, get_advice, max_score

        submission = self.submission
        definition = submission.questionnaire.definition
        code = submission.questionnaire.code
        answers = self._answers()
        level = self.level["level"]
        # The page reads its total, subscores and level from submission.result itself.
        return {
            "answers": answers,
            "max_score": max_score(code),
            "score_bar": score_bar(definition, self.total, level),
            "next_steps": definition.next_steps.get(level, ()),
            "advice": get_advice(level, code),
            # #363: 「無法判讀」 has nothing else saying why, so its advice is not folded away.
            "advice_open": level == UNKNOWN["level"],
            "support_message": definition.support(
                {answer.question.question_number: answer.score for answer in answers}
            ),
            "optional_ssq12": (
                Questionnaire.objects.filter(code=ssq12_tw.CODE).first()
                if code in (hhie_s.CODE, hhia_s.CODE) and submission.wearing_hearing_aid is False
                else None
            ),
        }


def score_bar(definition, score, level):
    # Ticket #158: a bar segmented by the thresholds, with a marker at this score's position.
    # "無法判讀" (no thresholds, or an out-of-range score) draws no bar.
    thresholds = definition.thresholds
    if level == "unknown" or not thresholds:
        return None
    ceiling = thresholds[-1][0]
    segments = []
    start = 0
    for upper, text, segment_level in thresholds:
        segments.append(
            {
                "level": segment_level,
                "color": definition.color(segment_level),
                "shade": definition.shade(segment_level),
                "text": text,
                "width": (upper - start) / ceiling * 100,
                "current": segment_level == level,
            }
        )
        start = upper
    position = max(0, min(100, score / ceiling * 100))
    return {
        "segments": segments,
        "position": position,
        "ceiling": ceiling,
        "current_text": next(segment["text"] for segment in segments if segment["current"]),
    }


class AverageResult(Result):
    """平均: the average of the items, no grade (SSQ12-TW)."""

    summary_template = "screening/summaries/average.html"
    row_template = "screening/record_rows/average.html"
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

    summary_template = "screening/summaries/norm.html"
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

    summary_template = "screening/summaries/subscale.html"
    row_template = "screening/record_rows/subscale.html"
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
