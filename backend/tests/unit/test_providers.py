import pytest
from pydantic import BaseModel

from app.llm.providers.base import (
    ImageBlock,
    LLMProvider,
    ProviderCapabilities,
    ProviderResult,
    ProviderUnsupportedError,
    ProviderUsage,
    SystemBlock,
)


class _Tiny(BaseModel):
    value: str


class FakeProvider:
    """Minimal in-memory LLMProvider used by every provider-layer test.
    Records the last call so tests can assert what client.py sent."""

    name = "fake"

    def __init__(self, parsed=None, usage=None, vision_input=True):
        self._parsed = parsed if parsed is not None else _Tiny(value="ok")
        self._usage = usage or ProviderUsage(input_tokens=10, output_tokens=5)
        self.capabilities = ProviderCapabilities(
            native_structured_output=True,
            prompt_caching=True,
            reports_token_usage=True,
            vision_input=vision_input,
        )
        self.calls: list[dict] = []

    def complete_structured(self, *, system_blocks, images, user_message, schema, model, max_tokens):
        self.calls.append(
            {
                "system_blocks": system_blocks,
                "images": images,
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
        images=[],
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


# --- Vision support (Phase 5: scanned-PDF pages sent as images) -----------
#
# Images always go through the SAME extract() entry point as text-only runs
# -- there's no separate "vision mode" code path, only an extra `images`
# argument that's empty on every non-scanned document.


def test_extract_passes_images_through_to_every_group(monkeypatch):
    monkeypatch.setattr(TORDocumentExtracted, "model_validate", staticmethod(lambda merged: merged))
    provider = FakeProvider(parsed=BasicInfoGroup.model_construct(), vision_input=True)
    group = FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="i")
    image = ImageBlock(page=1, media_type="image/png", data=b"fake-png-bytes")

    extract(document_text="d", provider=provider, model="m", groups=[group], images=[image])

    assert provider.calls[0]["images"] == [image]


def test_extract_with_no_images_sends_an_empty_list_not_none():
    """Every existing text-only call site relies on this -- `images` should
    never reach a provider as None, only as []."""
    provider = FakeProvider(parsed=BasicInfoGroup.model_construct())
    group = FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="i")

    _extract_one_group(provider, document_text="d", model="m", group=group, source_kind_rules="r")

    assert provider.calls[0]["images"] == []


def test_extract_refuses_to_start_when_a_resolved_provider_lacks_vision():
    """The check must run BEFORE any group is called -- a doomed run should
    not burn money on earlier groups before discovering a later group's
    resolved provider can't do vision."""
    no_vision = FakeProvider(parsed=BasicInfoGroup.model_construct(), vision_input=False)
    group = FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="i")
    image = ImageBlock(page=1, media_type="image/png", data=b"x")

    with pytest.raises(ProviderUnsupportedError, match="vision"):
        extract(document_text="d", provider=no_vision, model="m", groups=[group], images=[image])

    assert no_vision.calls == []


def test_extract_checks_every_group_override_for_vision_not_just_the_default():
    """A per-group TOR_GROUP_<NAME> override can name a different provider
    than the document default -- the vision check must catch a bad override
    even when the default provider itself supports vision, and must do so
    before the FIRST group (which uses the vision-capable default) runs."""
    has_vision = FakeProvider(parsed=BasicInfoGroup.model_construct(), vision_input=True)
    no_vision = FakeProvider(parsed=BasicInfoGroup.model_construct(), vision_input=False)
    groups = [
        FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="a"),
        FieldGroup(
            name="qualifications",
            schema=BasicInfoGroup,
            instruction="b",
            provider="weak",
            model="m2",
        ),
    ]
    image = ImageBlock(page=1, media_type="image/png", data=b"x")

    with pytest.raises(ProviderUnsupportedError, match="qualifications"):
        extract(
            document_text="d",
            provider=has_vision,
            model="m",
            groups=groups,
            provider_for=lambda name, _model: no_vision,
            images=[image],
        )

    # Neither group ran -- the default-provider group didn't get a head
    # start before the override was found to be incapable.
    assert has_vision.calls == []
    assert no_vision.calls == []


def test_extract_allows_vision_when_every_resolved_group_provider_supports_it(monkeypatch):
    monkeypatch.setattr(TORDocumentExtracted, "model_validate", staticmethod(lambda merged: merged))
    default_vision = FakeProvider(parsed=BasicInfoGroup.model_construct(), vision_input=True)
    override_vision = FakeProvider(parsed=BasicInfoGroup.model_construct(), vision_input=True)
    groups = [
        FieldGroup(name="basic_info", schema=BasicInfoGroup, instruction="a"),
        FieldGroup(
            name="qualifications",
            schema=BasicInfoGroup,
            instruction="b",
            provider="strong",
            model="m2",
        ),
    ]
    image = ImageBlock(page=1, media_type="image/png", data=b"x")

    extract(
        document_text="d",
        provider=default_vision,
        model="m",
        groups=groups,
        provider_for=lambda name, _model: override_vision,
        images=[image],
    )

    assert default_vision.calls[0]["images"] == [image]
    assert override_vision.calls[0]["images"] == [image]
