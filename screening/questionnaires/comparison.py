"""Wearing-status comparisons: one unaided and one aided record of the same questionnaire."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class TotalComparison:
    """The difference of the totals (HHIA-S, HHIE-S)."""

    anchor: str  # the report section id; bookmarks and family links point at it
    template = "screening/comparisons/total.html"
    history_template = "screening/comparisons/total_history.html"

    def records(self, submissions):
        return submissions.complete_hhi()

    def record_result(self, record):
        return f"{record.total_answer_score} 分"

    def difference(self, unaided, aided):
        return aided.total_answer_score - unaided.total_answer_score

    def difference_text(self, unaided, aided):
        change = self.difference(unaided, aided)
        if change < 0:
            return f"少了 {-change} 分"
        if change > 0:
            return f"多了 {change} 分"
        return "沒有變化"

    def summary(self, unaided, aided):
        return (
            f"沒戴 {unaided.total_answer_score} 分、有戴 {aided.total_answer_score} 分，"
            f"{self.difference_text(unaided, aided)}"
        )


@dataclass(frozen=True)
class AverageComparison:
    """The difference of the averages (SSQ12-TW); only records with all 12 items answered."""

    anchor: str  # the report section id; bookmarks and family links point at it
    template = "screening/comparisons/average.html"
    history_template = "screening/comparisons/average_history.html"

    def records(self, submissions):
        return submissions.with_scores().filter(answer_count=12)

    def record_result(self, record):
        if record.ssq_average is not None:
            return f"平均 {record.ssq_average} 分"
        return record.ssq_unavailable_reason

    def difference(self, unaided, aided):
        if unaided.ssq_average is None or aided.ssq_average is None:
            return None
        return (Decimal(aided.total_answer_score - unaided.total_answer_score) / 12).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )

    def difference_text(self, unaided, aided):
        change = self.difference(unaided, aided)
        if change is None:
            return "未計算整體差值：包含不適用題目或缺少完整回答"
        return f"{change:+.1f} 分"

    def summary(self, unaided, aided):
        return self.difference_text(unaided, aided)
