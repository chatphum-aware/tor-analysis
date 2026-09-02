"""Parse Thai number words into integers, e.g. "หนึ่งล้านห้าแสนบาทถ้วน" -> 1500000.

Per the project's hard rules, Thai TORs frequently write a money amount both
as digits and spelled out in words, and the two must be cross-checked in
code (never silently trust one over the other -- flag a mismatch instead).
This module only does the parsing; the cross-check + risk_flags logic lives
in derive/calculations.py (Step 3), which has both values to compare.

Scope: standard cardinal Thai number words up to ล้านล้าน (10^12), which
comfortably covers government procurement budgets. Does not handle
สตางค์ (satang/cents) or ordinal forms -- not needed for this domain.
"""
from __future__ import annotations

import re

_DIGIT_WORDS = {
    "ศูนย์": 0,
    "หนึ่ง": 1,
    "เอ็ด": 1,  # units-place "one" after a tens word, e.g. ยี่สิบเอ็ด = 21
    "สอง": 2,
    "ยี่": 2,  # "twenty" is ยี่สิบ, not สองสิบ
    "สาม": 3,
    "สี่": 4,
    "ห้า": 5,
    "หก": 6,
    "เจ็ด": 7,
    "แปด": 8,
    "เก้า": 9,
}

_SMALL_UNIT_WORDS = {
    "สิบ": 10,
    "ร้อย": 100,
    "พัน": 1_000,
    "หมื่น": 10_000,
    "แสน": 100_000,
}

_BIG_UNIT_WORDS = {
    "ล้าน": 1_000_000,
}

_ALL_WORDS = {**_DIGIT_WORDS, **_SMALL_UNIT_WORDS, **_BIG_UNIT_WORDS}
# Longest-match-first tokenization (e.g. "สิบ" before a shorter false match).
_WORDS_BY_LENGTH = sorted(_ALL_WORDS, key=len, reverse=True)
_TOKEN_RE = re.compile("|".join(re.escape(w) for w in _WORDS_BY_LENGTH))

# Trailing/leading words that commonly surround a money phrase but aren't
# part of the number itself.
_NOISE_WORDS = ("บาทถ้วน", "บาทพอดี", "บาท", "ถ้วน", "พอดี")


def _tokenize(text: str) -> list[str]:
    """Return the maximal contiguous run of recognized number-word tokens.

    Scans left to right; once a recognized token is found, keeps consuming
    recognized tokens for as long as they remain contiguous (allowing
    whitespace between them), stopping at the first unrecognized substring.
    """
    for word in _NOISE_WORDS:
        text = text.replace(word, " ")
    text = text.strip()

    tokens: list[str] = []
    pos = 0
    started = False
    while pos < len(text):
        if text[pos].isspace():
            pos += 1
            continue
        m = _TOKEN_RE.match(text, pos)
        if m:
            tokens.append(m.group(0))
            pos = m.end()
            started = True
            continue
        if started:
            break  # non-number content after a number run -- stop here
        pos += 1  # skip leading noise before the number starts
    return tokens


def _evaluate(tokens: list[str]) -> int | None:
    if not tokens:
        return None

    total = 0
    segment = 0
    current_digit: int | None = None

    for tok in tokens:
        if tok in _DIGIT_WORDS:
            current_digit = _DIGIT_WORDS[tok]
        elif tok in _SMALL_UNIT_WORDS:
            segment += (current_digit if current_digit is not None else 1) * _SMALL_UNIT_WORDS[tok]
            current_digit = None
        elif tok in _BIG_UNIT_WORDS:
            if current_digit is not None:
                segment += current_digit
                current_digit = None
            if segment == 0:
                segment = 1
            total += segment * _BIG_UNIT_WORDS[tok]
            segment = 0

    if current_digit is not None:
        segment += current_digit
    total += segment
    return total


def thai_number_words_to_int(text: str) -> int | None:
    """Parse Thai number words (optionally with a บาท/ถ้วน suffix) to an int.

    Returns None if no recognizable number-word run is found -- callers must
    treat that as "could not parse", not as zero.
    """
    tokens = _tokenize(text)
    return _evaluate(tokens)
