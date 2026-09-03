"""FieldGroup: pairs a Pydantic schema (a slice of the full document) with
the prompt fragment used to extract it.

v0.1 originally shipped ONE group covering the whole schema (the plan's
stated default: don't split until eval data shows it's needed). That
assumption did not survive contact with the API -- the first real call
against the full TORDocumentExtracted schema returned a 400
("compiled grammar is too large" / "Schema is too complex for
compilation"). Isolated live probes confirmed a flat list of ~13 identical
Sourced[str] fields compiles fine, and so does a single nested submodel
repeated 3x, but the full ~26-leaf mixed/nested schema does not. So the
split below happened immediately, on hard evidence, not speculatively.

Each entry stays within the shapes empirically confirmed to compile:
flat scalar groups, a single list-of-object field, or one submodel type
repeated a few times.

Groups run SEQUENTIALLY, never in parallel -- but a live measurement
disproved the original assumption that this would let calls 2-6 read the
document from cache. It doesn't: caching is a strict byte-prefix match,
and prefix order is tools/response-format -> system -> messages. Each
group's `output_format` is a DIFFERENT schema, so even though the system
blocks (rules, document text) are byte-identical across all 6 groups, the
varying schema ahead of them breaks the prefix match every time -- a real
6-call test showed cache_write>0 / cache_read=0 on every single group.
Two back-to-back calls using the SAME group's schema, by contrast, showed
cache_write=0 / cache_read=16075 on both -- full hits. So caching here
only helps a validation retry within one group, or re-running the same
document+group later (e.g. during eval), not the 6-groups-in-one-document
case this was originally designed for. Restoring cross-group caching would
need a schema-agnostic output_format shared by every group (e.g. a loosely
typed wrapper validated by Pydantic post-hoc instead of API-enforced
per-group grammar) -- not attempted in v0.1; flagged for a deliberate
decision rather than done speculatively.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from app.models.schema import (
    BasicInfoGroup,
    BondsGroup,
    DeliverablesGroup,
    KeyDatesGroup,
    MiscGroup,
    QualificationsGroup,
)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class FieldGroup:
    name: str
    schema: Type[BaseModel]
    instruction: str  # appended as the final, non-cached system block
    # Optional per-group override. Set when a group needs a different
    # provider/model than the document default -- eval showed cheap models
    # break the source/null rules on the list-heavy groups while handling the
    # flat ones fine. None means "use the document default".
    provider: str | None = None
    model: str | None = None


def _load(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


# Shared cached prefix -- identical across every group call.
SHARED_RULES = _load("extract_system.md")

# Rule #2's locator format depends on the source document's format, so that
# part of the prompt is split per kind: a PDF call must never be told about
# spreadsheet cell refs, and an XLSX call must never be told to cite a page
# it doesn't have. Also constant across all 6 group calls, so it sits in the
# cacheable prefix alongside SHARED_RULES.
SOURCE_KIND_RULES: dict[str, str] = {
    "pdf": _load("source_kind_pdf.md"),
    "docx": _load("source_kind_docx.md"),
    "xlsx": _load("source_kind_xlsx.md"),
}

FIELD_GROUPS: list[FieldGroup] = [
    FieldGroup("basic_info", BasicInfoGroup, _load("group_basic_info.md")),
    FieldGroup("key_dates", KeyDatesGroup, _load("group_key_dates.md")),
    FieldGroup("bonds", BondsGroup, _load("group_bonds.md")),
    FieldGroup("qualifications", QualificationsGroup, _load("group_qualifications.md")),
    FieldGroup("deliverables", DeliverablesGroup, _load("group_deliverables.md")),
    FieldGroup("misc", MiscGroup, _load("group_misc.md")),
]


def apply_group_overrides(
    groups: list[FieldGroup], overrides: dict[str, tuple[str, str]]
) -> list[FieldGroup]:
    """Return a new list with each group's provider/model swapped in from
    `overrides` (keyed by group name, e.g. Config.group_overrides). Groups
    not named in `overrides` are returned unchanged. `FieldGroup` is frozen,
    so this builds new instances rather than mutating in place."""
    result = []
    for group in groups:
        override = overrides.get(group.name)
        if override is None:
            result.append(group)
        else:
            provider, model = override
            result.append(replace(group, provider=provider, model=model))
    return result
