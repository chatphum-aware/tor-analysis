import pytest

from app.llm.providers.base import ProviderUnsupportedError
from app.llm.providers.registry import PROVIDER_NAMES, get_provider


def test_anthropic_is_registered():
    assert "anthropic" in PROVIDER_NAMES


def test_unknown_provider_is_rejected_with_the_valid_list():
    with pytest.raises(ProviderUnsupportedError) as exc:
        get_provider("not-a-provider", api_key="x")
    assert "not-a-provider" in str(exc.value)
    for name in PROVIDER_NAMES:
        assert name in str(exc.value)


def test_anthropic_provider_declares_required_capabilities():
    provider = get_provider("anthropic", api_key="test-key-not-used")
    assert provider.name == "anthropic"
    assert provider.capabilities.native_structured_output is True
    assert provider.capabilities.prompt_caching is True


def test_openai_is_registered_and_declares_structured_output():
    provider = get_provider("openai", api_key="test-key-not-used")
    assert provider.name == "openai"
    assert provider.capabilities.native_structured_output is True
    assert provider.capabilities.prompt_caching is False  # no explicit cache_control API


def test_gemini_is_registered_and_declares_structured_output():
    provider = get_provider("gemini", api_key="test-key-not-used")
    assert provider.name == "gemini"
    assert provider.capabilities.native_structured_output is True


def test_openai_compat_requires_a_base_url():
    """Without base_url this would silently talk to api.openai.com with a
    local-endpoint key, which is both confusing and a key-leak risk."""
    from app.llm.providers.openai_compat_provider import OpenAICompatProvider

    with pytest.raises(ProviderUnsupportedError) as exc:
        OpenAICompatProvider(api_key="x", base_url=None, probe=False)
    assert "TOR_PROVIDER_BASE_URL" in str(exc.value)


def test_openai_compat_reports_no_usage_confidence_by_default():
    """Self-hosted stacks frequently return zeroed or absent usage, which must
    surface as 'cost unknown' rather than 'cost zero'."""
    from app.llm.providers.openai_compat_provider import OpenAICompatProvider

    provider = OpenAICompatProvider(
        api_key="x", base_url="http://localhost:11434/v1", probe=False
    )
    assert provider.name == "openai_compat"
    assert provider.capabilities.prompt_caching is False
