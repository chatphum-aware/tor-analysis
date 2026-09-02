"""Score live Claude extractions of the eval fixtures against hand-annotated
tests/expected/*.json ground truth (Step 6 of the plan).

Per-field verdicts: exact / wrong / missed / hallucinated -- reported as raw
counts, not percentages (n=3 documents is too small to honestly claim a %,
per the plan's explicit call on this).

Exclusions from scoring, and why:
  - `extraction_meta` (usage/cost/duration) is dropped entirely -- it changes
    on every single run by design, so scoring it would always show "wrong".
  - `risk_flags` is reported as a separate count (expected vs. actual), not
    scored leaf-by-leaf -- unlike every other field, a risk flag's `text` is
    free-form model-generated prose, not an extracted fact. Comparing it
    against this script's own ground-truth wording would mostly measure
    phrasing overlap, not whether the model noticed the right thing.
  - `source`/`confidence`/`reason` are never compared -- only `.value`. The
    plan's exact/wrong/missed/hallucinated categories are about the
    extracted fact itself.

List fields (key_dates, qualifications, deliverables, required_documents)
are matched by content, not position: each list item is reduced to a
representative text (its `text`/`phase`/`type`/`.value`, whichever the item
shape has) and expected/actual items are greedily paired by text similarity
(exact-substring or character-bigram overlap), highest-similarity pairs
first. This exists because an earlier index-based version (expected[i] vs
actual[i]) scored a whole list as "wrong" whenever the model returned a
different number of items than the curated ground truth, even when the
actual content was fine -- see PROGRESS.md for the incident. An unmatched
expected item scores as fully missed; an unmatched actual item (the model
found more than curated ground truth expected) is reported separately as
an "extra" count, not folded into hallucinated -- it may be a genuinely
valid finding the ground truth simply didn't enumerate.

String equality is intentionally lenient: normalized (whitespace-collapsed)
substring containment in either direction counts as "exact" -- e.g. ground
truth "กรมสรรพากร" matches model output "กรมสรรพากร โดยสำนักงานสรรพากรภาค 1".
This mirrors how a human grader would treat a superset/subset free-text
answer, at the cost of being unable to catch an overly-vague answer that
happens to contain the right substring.

Usage:
    ANTHROPIC_API_KEY=... python -m app.eval.run_eval [--model claude-haiku-4-5]

Costs real Claude API money -- one extraction run per fixture in
tests/expected/*.json (each with a matching outputs/samples/<id>.pdf from
fetch_samples.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import load_config
from app.derive.calculations import assemble_document
from app.derive.pricing import Cost, Usage, compute_cost
from app.llm.client import ExtractionValidationError, extract
from app.llm.groups import FIELD_GROUPS
from app.pdf.extract import build_document_text, extract_document

EXPECTED_DIR = Path(__file__).resolve().parents[2] / "tests" / "expected"
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "outputs" / "samples"
ACTUAL_DIR = Path(__file__).resolve().parents[2] / "outputs" / "eval"

_SOURCED_KEYS = {"value", "source", "confidence", "reason"}
_EXCLUDED_TOP_LEVEL_KEYS = {"risk_flags"}
_MATCH_THRESHOLD = 0.3  # min text similarity to pair a list item across expected/actual

Verdict = str  # "exact" | "wrong" | "missed" | "hallucinated"


@dataclass
class FieldTally:
    exact: int = 0
    wrong: int = 0
    missed: int = 0
    hallucinated: int = 0

    def add(self, verdict: Verdict) -> None:
        setattr(self, verdict, getattr(self, verdict) + 1)

    @property
    def total(self) -> int:
        return self.exact + self.wrong + self.missed + self.hallucinated


def _norm(value):
    if isinstance(value, str):
        return " ".join(value.split()).strip()
    if isinstance(value, float):
        return round(value, 2)
    return value


def _classify_leaf(expected_value, actual_value) -> Verdict:
    if expected_value is None and actual_value is None:
        return "exact"
    if expected_value is None and actual_value is not None:
        return "hallucinated"
    if expected_value is not None and actual_value is None:
        return "missed"
    e, a = _norm(expected_value), _norm(actual_value)
    if isinstance(e, str) and isinstance(a, str):
        if e == a or (e and e in a) or (a and a in e):
            return "exact"
        return "wrong"
    return "exact" if e == a else "wrong"


def _is_sourced(node) -> bool:
    return isinstance(node, dict) and _SOURCED_KEYS.issubset(node.keys())


def _primary_text(item) -> str:
    """Best-effort text representative of a list item, for similarity matching."""
    if _is_sourced(item):
        return str(item.get("value") or "")
    if isinstance(item, dict):
        for key in ("text", "phase", "type", "description"):
            val = item.get(key)
            if _is_sourced(val) and val.get("value"):
                return str(val["value"])
        parts = [
            str(v["value"])
            for v in item.values()
            if _is_sourced(v) and isinstance(v.get("value"), (str, int, float))
        ]
        return " ".join(parts)
    return str(item)


def _bigrams(s: str) -> set[str]:
    return {s[i : i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


def _similarity(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    sa, sb = _bigrams(a), _bigrams(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _match_items(expected_list: list, actual_list: list) -> tuple[list[tuple[int, int | None]], list[int]]:
    """Greedy best-match pairing of expected[i] to actual[j] by content
    similarity (highest-similarity pairs claimed first). Returns
    (pairs, unmatched_actual_indices): pairs covers every expected index
    (act index or None if nothing matched well enough); unmatched_actual
    lists actual items nothing expected claimed (extras)."""
    exp_texts = [_primary_text(e) for e in expected_list]
    act_texts = [_primary_text(a) for a in actual_list]
    scored = [
        (_similarity(et, at), i, j)
        for i, et in enumerate(exp_texts)
        for j, at in enumerate(act_texts)
    ]
    scored = [s for s in scored if s[0] >= _MATCH_THRESHOLD]
    scored.sort(key=lambda s: s[0], reverse=True)

    matched_exp: dict[int, int] = {}
    used_act: set[int] = set()
    for _sim, i, j in scored:
        if i in matched_exp or j in used_act:
            continue
        matched_exp[i] = j
        used_act.add(j)

    pairs = [(i, matched_exp.get(i)) for i in range(len(expected_list))]
    unmatched_actual = [j for j in range(len(actual_list)) if j not in used_act]
    return pairs, unmatched_actual


def _walk(path: str, expected, actual, tallies: dict[str, FieldTally], mismatches: list[str]) -> None:
    if _is_sourced(expected):
        actual_value = actual.get("value") if isinstance(actual, dict) else None
        tallies.setdefault(path, FieldTally()).add(_classify_leaf(expected["value"], actual_value))
        return

    if isinstance(expected, dict):
        for key, exp_val in expected.items():
            act_val = actual.get(key) if isinstance(actual, dict) else None
            _walk(f"{path}.{key}" if path else key, exp_val, act_val, tallies, mismatches)
        return

    if isinstance(expected, list):
        actual_list = actual if isinstance(actual, list) else []
        pairs, unmatched_actual = _match_items(expected, actual_list)
        unmatched_expected = sum(1 for _, j in pairs if j is None)
        if unmatched_expected or unmatched_actual:
            mismatches.append(
                f"{path}: {len(expected)} expected, {len(actual_list)} actual "
                f"-- {unmatched_expected} expected item(s) unmatched (missed), "
                f"{len(unmatched_actual)} actual item(s) extra (not penalized)"
            )
        for exp_idx, act_idx in pairs:
            act_item = actual_list[act_idx] if act_idx is not None else None
            _walk(f"{path}[]", expected[exp_idx], act_item, tallies, mismatches)
        return

    tallies.setdefault(path, FieldTally()).add(_classify_leaf(expected, actual))


def score_document(expected: dict, actual: dict) -> tuple[dict[str, FieldTally], list[str], tuple[int, int]]:
    tallies: dict[str, FieldTally] = {}
    mismatches: list[str] = []
    for key, exp_val in expected.items():
        if key in _EXCLUDED_TOP_LEVEL_KEYS:
            continue
        _walk(key, exp_val, actual.get(key), tallies, mismatches)
    risk_flags_count = (len(expected.get("risk_flags", [])), len(actual.get("risk_flags", [])))
    return tallies, mismatches, risk_flags_count


def _merge(total: dict[str, FieldTally], part: dict[str, FieldTally]) -> None:
    for k, v in part.items():
        t = total.setdefault(k, FieldTally())
        t.exact += v.exact
        t.wrong += v.wrong
        t.missed += v.missed
        t.hallucinated += v.hallucinated


def render_markdown(
    total: dict[str, FieldTally],
    sample_count: int,
    total_cost: Cost | None,
    risk_flag_counts: list[tuple[str, int, int]],
    mismatches: list[str],
) -> str:
    lines = [
        f"# TOR extraction eval -- {sample_count} document(s)",
        "",
        "Counts, not percentages -- n is too small to honestly claim a %.",
        "",
        "| Field | Exact | Wrong | Missed | Hallucinated |",
        "|---|---|---|---|---|",
    ]
    worst_first = sorted(
        total.items(),
        key=lambda kv: (kv[1].wrong + kv[1].missed + kv[1].hallucinated, kv[0]),
        reverse=True,
    )
    for field_path, t in worst_first:
        lines.append(f"| `{field_path}` | {t.exact} | {t.wrong} | {t.missed} | {t.hallucinated} |")

    grand = FieldTally()
    for t in total.values():
        grand.exact += t.exact
        grand.wrong += t.wrong
        grand.missed += t.missed
        grand.hallucinated += t.hallucinated

    lines += [
        "",
        f"**Total leaf fields scored:** {grand.total} across {sample_count} document(s)  ",
        f"**Exact:** {grand.exact}  **Wrong:** {grand.wrong}  **Missed:** {grand.missed}  **Hallucinated:** {grand.hallucinated}",
    ]

    lines += ["", "## risk_flags (not leaf-scored -- see module docstring)", ""]
    lines += ["| Document | Expected count | Actual count |", "|---|---|---|"]
    for sample_id, exp_n, act_n in risk_flag_counts:
        lines.append(f"| {sample_id} | {exp_n} | {act_n} |")

    if mismatches:
        lines += ["", "## List length mismatches (scored only up to the shorter length)", ""]
        lines += [f"- {m}" for m in mismatches]

    if total_cost is not None:
        lines += [
            "",
            f"**Total cost this eval run:** ${total_cost.usd:.4f} USD "
            f"(~฿{total_cost.thb:.2f} @ {total_cost.usd_thb_rate}, "
            f"model pricing as of {total_cost.pricing_as_of})",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="override TOR_MODEL env var")
    args = parser.parse_args(argv)

    config = load_config()
    model = args.model or config.model
    if not config.anthropic_api_key:
        print("error: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 1

    expected_files = sorted(EXPECTED_DIR.glob("*.json"))
    if not expected_files:
        print(f"error: no ground-truth files found in {EXPECTED_DIR}", file=sys.stderr)
        return 1

    total_tallies: dict[str, FieldTally] = {}
    all_mismatches: list[str] = []
    risk_flag_counts: list[tuple[str, int, int]] = []
    total_usage = Usage(0, 0, 0, 0)
    scored = 0

    for expected_path in expected_files:
        sample_id = expected_path.stem
        pdf_path = SAMPLES_DIR / f"{sample_id}.pdf"
        if not pdf_path.exists():
            print(f"skip {sample_id}: {pdf_path} not found -- run fetch_samples.py first", file=sys.stderr)
            continue

        expected = json.loads(expected_path.read_text(encoding="utf-8"))

        print(f"extracting {sample_id} ({model}) ...")
        result = extract_document(str(pdf_path))
        document_text = build_document_text(result.blocks)
        try:
            run = extract(
                document_text=document_text,
                api_key=config.anthropic_api_key,
                model=model,
                groups=FIELD_GROUPS,
            )
        except ExtractionValidationError as exc:
            print(f"  ERROR: {sample_id} failed extraction: {exc}", file=sys.stderr)
            continue

        doc = assemble_document(
            run.document,
            scan_report=result.scan_report,
            model=run.model,
            usage=run.usage,
            duration_ms=run.duration_ms,
        )
        actual = json.loads(doc.model_dump_json(exclude={"extraction_meta"}))

        ACTUAL_DIR.mkdir(parents=True, exist_ok=True)
        actual_path = ACTUAL_DIR / f"{sample_id}_{model}.json"
        actual_path.write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")

        tallies, mismatches, (exp_n, act_n) = score_document(expected, actual)
        _merge(total_tallies, tallies)
        all_mismatches += [f"{sample_id}: {m}" for m in mismatches]
        risk_flag_counts.append((sample_id, exp_n, act_n))

        total_usage.input_tokens += run.usage.input_tokens
        total_usage.output_tokens += run.usage.output_tokens
        total_usage.cache_creation_input_tokens += run.usage.cache_creation_input_tokens
        total_usage.cache_read_input_tokens += run.usage.cache_read_input_tokens
        scored += 1

    if scored == 0:
        print("error: nothing was scored", file=sys.stderr)
        return 1

    total_cost = compute_cost(model, total_usage)
    report = render_markdown(total_tallies, scored, total_cost, risk_flag_counts, all_mismatches)
    print()
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
