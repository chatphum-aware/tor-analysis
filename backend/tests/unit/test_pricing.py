from app.derive.pricing import Usage, compute_cost


def test_haiku_cost_is_computed_from_the_anthropic_table():
    cost = compute_cost("anthropic", "claude-haiku-4-5", Usage(1_000_000, 1_000_000))
    assert cost is not None
    assert cost.provider == "anthropic"
    assert cost.usd == 6.0  # 1.00 input + 5.00 output per Mtok


def test_cache_write_and_read_use_the_documented_multipliers():
    usage = Usage(
        input_tokens=0,
        output_tokens=0,
        cache_write_tokens=1_000_000,
        cached_read_tokens=1_000_000,
    )
    cost = compute_cost("anthropic", "claude-haiku-4-5", usage)
    assert cost is not None
    assert cost.usd == 1.35  # 1.00*1.25 write + 1.00*0.10 read


def test_unknown_model_returns_none_rather_than_guessing():
    assert compute_cost("anthropic", "some-future-model", Usage(1, 1)) is None


def test_same_model_name_on_a_different_provider_is_not_silently_reused():
    """A bare model name is not globally unique -- 'llama-3.1-70b' costs
    different amounts on Together vs Groq vs a local GPU."""
    assert compute_cost("openai_compat", "claude-haiku-4-5", Usage(1, 1)) is None


def test_thb_conversion_reports_the_rate_it_used():
    cost = compute_cost("anthropic", "claude-haiku-4-5", Usage(1, 1))
    assert cost is not None
    assert cost.thb == round(cost.usd * cost.usd_thb_rate, 4)
    assert cost.rate_source_date


def test_gemini_pricing_entry_resolves():
    cost = compute_cost("gemini", "gemini-3.6-flash", Usage(1_000_000, 1_000_000))
    assert cost is not None
    assert cost.provider == "gemini"
    assert cost.usd == 4.5  # 0.75 input + 3.75 output per Mtok
