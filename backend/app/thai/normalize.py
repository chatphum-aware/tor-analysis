"""Thai-specific text normalization.

Per the project's hard rules:
  - NFC normalize everything (PyMuPDF text extraction from Thai fonts can
    yield decomposed / oddly-ordered combining marks).
  - Thai digits ๐-๙ must become Arabic 0-9.
  - Buddhist Era years must be convertible to Common Era (พ.ศ. - 543 = ค.ศ.).

This module does NOT guess or silently "fix" anything it can't verify --
`find_glyph_order_anomalies` only *reports* suspicious spots for a human to
look at (per Step 1 of the plan: log examples of mangled vowels/tone marks).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

_THAI_DIGIT_MAP = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

# Thai combining marks that must follow a base consonant. If one of these
# appears at the start of a string/line, or two appear back-to-back with no
# base consonant between them, the extraction almost certainly scrambled
# glyph order (a known failure mode of some Thai font subsets in PDFs).
_THAI_COMBINING_MARKS = (
    "ั"  # MAI HAN-AKAT
    "ิีึื"  # SARA I, II, UE, UEE
    "ุู"  # SARA U, UU
    "ฺ"  # PHINTHU
    "็่้๊๋์ํ๎"  # MAITAIKHU, tone marks, THANTHAKHAT, NIKHAHIT, YAMAKKAN
)
_THAI_CONSONANT_RANGE = ("ก", "ฮ")  # ก .. ฮ


def normalize_text(text: str) -> str:
    """NFC-normalize and convert Thai digits to Arabic digits.

    Does not touch Buddhist-Era years -- that conversion is contextual
    (needs to know "this number is a year") and belongs to numbers.py /
    the schema layer, not blind text normalization.
    """
    if not text:
        return text
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_THAI_DIGIT_MAP)
    return text


def be_to_ce(be_year: int) -> int:
    """Convert a Buddhist Era year to Common Era. 2569 -> 2026."""
    return be_year - 543


@dataclass
class GlyphAnomaly:
    context: str  # a short window of text around the anomaly, for a human to eyeball
    reason: str


def find_glyph_order_anomalies(text: str, *, context_chars: int = 20) -> list[GlyphAnomaly]:
    """Flag spots where a *run* of combining marks has no base consonant before it.

    Real Thai commonly stacks multiple combining marks on one consonant
    (e.g. "กลุ่ม" = ก, ล, ุ [SARA U], ่ [MAI EK] -- the tone mark follows the
    vowel, not the consonant directly). So only the *start* of a run of
    combining marks needs a consonant immediately before it; a combining
    mark following another combining mark is normal and not checked.

    This is a detector, not a fixer -- per the project's rules, ambiguous
    extraction quality must be surfaced to a human (logged), never silently
    "corrected" by guessing what the original glyph order was.
    """
    anomalies: list[GlyphAnomaly] = []
    for i, ch in enumerate(text):
        if ch not in _THAI_COMBINING_MARKS:
            continue
        prev = text[i - 1] if i > 0 else ""
        if prev in _THAI_COMBINING_MARKS:
            continue  # mid-run stacking (e.g. vowel + tone mark) -- normal
        prev_is_consonant = _THAI_CONSONANT_RANGE[0] <= prev <= _THAI_CONSONANT_RANGE[1]
        if not prev_is_consonant:
            start = max(0, i - context_chars)
            end = min(len(text), i + context_chars)
            anomalies.append(
                GlyphAnomaly(
                    context=text[start:end],
                    reason=f"combining-mark run starting with {ch!r} (U+{ord(ch):04X}) has no preceding Thai consonant",
                )
            )
    return anomalies
