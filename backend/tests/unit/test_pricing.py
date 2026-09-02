from app.derive.pricing import Usage, compute_cost


def test_basic_cost_no_cache():
    usage = Usage(input_tokens=1000, output_tokens=500)
    cost = compute_cost("claude-haiku-4-5", usage)
    assert cost is not None
    # (1000 * $1.00 + 500 * $5.00) / 1_000_000
    assert cost.usd == 0.0035


def test_cache_write_and_read_multipliers():
    usage = Usage(
        input_tokens=0,
        output_tokens=0,
        cache_creation_input_tokens=1000,
        cache_read_input_tokens=1000,
    )
    cost = compute_cost("claude-haiku-4-5", usage)
    assert cost is not None
    # write: 1000 * $1.00 * 1.25 / 1e6 = 0.00125
    # read:  1000 * $1.00 * 0.10 / 1e6 = 0.0001
    assert cost.usd == round(0.00125 + 0.0001, 6)


def test_unknown_model_returns_none_not_a_guess():
    usage = Usage(input_tokens=1000, output_tokens=500)
    assert compute_cost("some-future-model-not-in-table", usage) is None


def test_thb_uses_env_rate(monkeypatch):
    monkeypatch.setenv("USD_THB_RATE", "40.0")
    monkeypatch.setenv("USD_THB_RATE_DATE", "2026-01-01")
    usage = Usage(input_tokens=1_000_000, output_tokens=0)
    cost = compute_cost("claude-haiku-4-5", usage)
    assert cost is not None
    assert cost.usd == 1.0
    assert cost.thb == 40.0
    assert cost.usd_thb_rate == 40.0
    assert cost.rate_source_date == "2026-01-01"


def test_cost_is_always_marked_as_estimate():
    cost = compute_cost("claude-haiku-4-5", Usage(input_tokens=1, output_tokens=1))
    assert cost is not None
    assert cost.is_estimate is True
