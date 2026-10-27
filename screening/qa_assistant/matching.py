"""Typed questions matched to the FAQ (#399, spec #396).

In memory with the standard library only, no database or outside service (#374): the typed
question and each way of asking a FAQ (its question and other phrasings) are normalised, their
colloquial words swapped for the standard ones (content.SYNONYMS), then cut into overlapping
pairs of characters, which needs no word breaking for Chinese.
"""

import re
import unicodedata

from screening.qa_assistant import content

# A FAQ matches when this share of the typed question's pairs is in one of its ways of asking.
# Strict on purpose: better 沒有找到 than a wrong answer (spec #396 story 44). Tuned with the
# owner's test set once it has 30–50 questions (ADR 0034).
THRESHOLD = 0.6


def match(text):
    """The codes of the FAQs matching a typed question, the best first; [] when none does."""
    asked = _pairs(text)
    if not asked:
        return []
    scored = []
    for order, faq in enumerate(content.FAQS):
        score = max(_score(asked, _pairs(way)) for way in (faq.question, *faq.other_phrasings))
        if score[0] >= THRESHOLD:
            scored.append((score, -order, faq.code))
    return [code for _, _, code in sorted(scored, reverse=True)]


def _score(asked, way):
    shared = len(asked & way)
    # How much of the typed question is in this way of asking; on a tie, the closer one.
    return shared / len(asked), shared / len(asked | way)


def _pairs(text):
    words = _standard_words(_normalise(text))
    return {words[i : i + 2] for i in range(len(words) - 1)}


def _normalise(text):
    # NFKC turns full-width letters, digits and spaces half-width; then only letters and digits
    # are kept, so punctuation and spaces change nothing.
    return "".join(char for char in unicodedata.normalize("NFKC", text).lower() if char.isalnum())


# Built once, when the module loads: the colloquial words normalised like the typed question.
_SYNONYMS = {_normalise(word): standard for word, standard in content.SYNONYMS.items()}
# The longest word first, so a longer colloquial word wins over one inside it.
_COLLOQUIAL = re.compile("|".join(map(re.escape, sorted(_SYNONYMS, key=len, reverse=True))))


def _standard_words(text):
    return _COLLOQUIAL.sub(lambda found: _SYNONYMS[found[0]], text)
