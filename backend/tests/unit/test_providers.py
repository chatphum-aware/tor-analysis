from pydantic import BaseModel

from app.llm.providers.base import (
    LLMProvider,
    ProviderCapabilities,
    ProviderResult,
    ProviderUsage,
    SystemBlock,
)


class _Tiny(BaseModel):
    value: str


class FakeProvider:
    """Minimal in-memory LLMProvider used by every provider-layer test.
    Records the last call so tests can assert what client.py sent."""

    name = "fake"
    capabilities = ProviderCapabilities(
        native_structured_output=True, prompt_caching=True, reports_token_usage=True
    )

    def __init__(self, parsed=None, usage=None):
        self._parsed = parsed if parsed is not None else _Tiny(value="ok")
        self._usage = usage or ProviderUsage(input_tokens=10, output_tokens=5)
        self.calls: list[dict] = []

    def complete_structured(self, *, system_blocks, user_message, schema, model, max_tokens):
        self.calls.append(
            {
                "system_blocks": system_blocks,
                "user_message": user_message,
                "schema": schema,
                "model": model,
                "max_tokens": max_tokens,
            }
        )
        return ProviderResult(parsed=self._parsed, usage=self._usage)


def test_fake_provider_satisfies_protocol():
    assert isinstance(FakeProvider(), LLMProvider)


def test_system_block_defaults_to_not_cacheable():
    assert SystemBlock(text="hello").cacheable is False


def test_provider_usage_defaults_cache_fields_to_zero():
    usage = ProviderUsage(input_tokens=3, output_tokens=4)
    assert usage.cache_write_tokens == 0
    assert usage.cached_read_tokens == 0


def test_complete_structured_returns_parsed_and_usage():
    provider = FakeProvider()
    result = provider.complete_structured(
        system_blocks=[SystemBlock(text="rules", cacheable=True)],
        user_message="go",
        schema=_Tiny,
        model="fake-1",
        max_tokens=100,
    )
    assert result.parsed.value == "ok"
    assert result.usage.input_tokens == 10
    assert provider.calls[0]["model"] == "fake-1"


from app.llm.client import _extract_one_group, extract
from app.llm.groups import FieldGroup
from app.models.schema import BasicInfoGroup, TORDocumentExtracted


def test_one_group_sends_shared_rules_and_document_as_cacheable_blocks():
    """The two big blocks must stay cacheable and in this order -- prompt
    caching is a strict byte-prefix match, so reordering silently destroys
    every cache hit (see llm/groups.py's measured findings). Tested at the
    per-group level: extract() requires a complete TORDocumentExtracted from
    ALL groups combined (unchanged from before this refactor), so a
    single-group FakeProvider can't go through the full extract() call."""
    provider = FakeProvider(parsed=BasicInfoGroup.model_construct())
    group = FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="do the thing")

    _extract_one_group(
        provider, document_text="DOC TEXT", model="m", group=group, source_kind_rules="SOURCE RULES"
    )

    blocks = provider.calls[0]["system_blocks"]
    # shared rules + per-format source rules + document all cacheable; only the
    # per-group instruction (which differs per call) is not.
    assert [b.cacheable for b in blocks] == [True, True, True, False]
    assert blocks[1].text == "SOURCE RULES"
    assert blocks[2].text == "DOC TEXT"
    assert blocks[3].text == "do the thing"


def test_one_group_passes_group_schema_through_untouched():
    provider = FakeProvider(parsed=BasicInfoGroup.model_construct())
    group = FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="i")

    _extract_one_group(
        provider, document_text="d", model="m", group=group, source_kind_rules="SOURCE RULES"
    )

    assert provider.calls[0]["schema"] is BasicInfoGroup


def test_extract_merges_all_groups_into_one_validated_document():
    """The end-to-end orchestrator DOES require every group's fields, because
    it validates the merge against the full TORDocumentExtracted schema --
    this is existing, preserved behavior, not new in this refactor."""
    null_field = {"value": None, "source": None, "confidence": "low", "reason": "n/a"}
    empty_bond = {"amount": null_field, "percent_stated": null_field, "accepted_forms": null_field}
    full_doc = {
        "project_name": null_field,
        "project_id": null_field,
        "agency": null_field,
        "announcement_date": null_field,
        "procurement_method": null_field,
        "budget_amount": null_field,
        "median_price": null_field,
        "key_dates": [],
        "bid_bond": empty_bond,
        "contract_bond": empty_bond,
        "warranty_bond": empty_bond,
        "qualifications": [],
        "deliverables": [],
        "penalty": {"rate_percent_per_day": null_field, "cap_percent": null_field},
        "required_documents": [],
        "evaluation_criteria": {
            "method": null_field,
            "price_weight": null_field,
            "technical_weight": null_field,
            "sub_criteria": null_field,
        },
        "risk_flags": [],
        "contact": {
            "name_redacted": null_field,
            "department": null_field,
            "phone": null_field,
            "email": null_field,
        },
    }
    provider = FakeProvider(parsed=TORDocumentExtracted.model_validate(full_doc))
    group = FieldGroup(name="everything", schema=TORDocumentExtracted, instruction="i")

    result = extract(document_text="d", provider=provider, model="m", groups=[group])

    assert isinstance(result.document, TORDocumentExtracted)
    assert result.model == "m"


def test_group_override_selects_a_different_provider_and_model(monkeypatch):
    """Eval evidence (2026-09-02): cheap models violate the source/null rules
    in qualifications/key_dates/misc/deliverables but are fine elsewhere, so
    the model must be selectable per group, not per document.

    Bypasses the final TORDocumentExtracted.model_validate here -- this test
    is about provider ROUTING per group, not document completeness (that's
    covered separately by test_extract_merges_all_groups_into_one_validated_document).
    Two BasicInfoGroup-shaped groups don't cover the full schema, and that's
    fine: it's not what this test is checking."""
    monkeypatch.setattr(TORDocumentExtracted, "model_validate", staticmethod(lambda merged: merged))

    cheap = FakeProvider(parsed=BasicInfoGroup.model_construct())
    strong = FakeProvider(parsed=BasicInfoGroup.model_construct())
    providers = {"cheap": cheap, "strong": strong}

    groups = [
        FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="a"),
        FieldGroup(
            name="qualifications",
            schema=BasicInfoGroup,
            instruction="b",
            provider="strong",
            model="big-model",
        ),
    ]

    extract(
        document_text="d",
        provider=cheap,
        model="small-model",
        groups=groups,
        provider_for=lambda name, _model: providers[name],
    )

    assert len(cheap.calls) == 1
    assert cheap.calls[0]["model"] == "small-model"
    assert len(strong.calls) == 1
    assert strong.calls[0]["model"] == "big-model"


def test_group_without_override_uses_the_default_provider():
    default = FakeProvider(parsed=BasicInfoGroup.model_construct())
    group = FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="a")

    _extract_one_group(
        default, document_text="d", model="m", group=group, source_kind_rules="SOURCE RULES"
    )

    assert len(default.calls) == 1


def test_apply_group_overrides_replaces_only_named_groups():
    from app.llm.groups import apply_group_overrides

    groups = [
        FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="a"),
        FieldGroup(name="qualifications", schema=BasicInfoGroup, instruction="b"),
    ]
    result = apply_group_overrides(groups, {"qualifications": ("anthropic", "claude-opus-5")})

    assert result[0].provider is None and result[0].model is None
    assert result[1].provider == "anthropic"
    assert result[1].model == "claude-opus-5"
    # original list is untouched -- FieldGroup is frozen, this builds new instances
    assert groups[1].provider is None


def test_apply_group_overrides_is_a_noop_with_no_matching_overrides():
    from app.llm.groups import apply_group_overrides

    groups = [FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="a")]
    result = apply_group_overrides(groups, {"qualifications": ("anthropic", "claude-opus-5")})

    assert result[0].provider is None
    assert result[0].model is None


def test_api_key_for_provider_reads_the_right_env_var(monkeypatch):
    from app.config import api_key_for_provider

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert api_key_for_provider("openai") == "sk-openai-test"
    assert api_key_for_provider("anthropic") is None
