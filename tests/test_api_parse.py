"""Unit tests for Cursor usage payload parsing."""

from __future__ import annotations

from cursor_usage.api import (
    _cookie_header_value,
    _iso_to_epoch_ms,
    parse_aggregated_usage,
    parse_usage_summary,
)


def test_parse_usage_summary(usage_summary_payload: dict) -> None:
    """Plan and on-demand fields are normalized from usage-summary."""
    data = parse_usage_summary(usage_summary_payload)

    assert data.membership_type == "pro"
    assert data.billing_cycle_start == "2026-04-02T14:11:55.000Z"
    assert data.plan.enabled is True
    assert data.plan.used == 1500
    assert data.plan.limit == 2000
    assert data.plan.remaining == 500
    assert data.plan.auto_percent_used == 1.24
    assert data.plan.api_percent_used == 3.0
    assert data.plan.total_percent_used == 1.24
    assert data.on_demand.enabled is True
    assert data.on_demand.used == 2309
    assert data.on_demand.limit is None
    assert data.models == []


def test_parse_usage_summary_empty() -> None:
    """Missing individualUsage still yields a usable object."""
    data = parse_usage_summary({})

    assert data.plan.enabled is False
    assert data.plan.used is None
    assert data.on_demand.enabled is False
    assert data.membership_type is None


def test_parse_aggregated_usage(aggregated_payload: dict) -> None:
    """Models are sorted by cost and totals are extracted."""
    models, totals = parse_aggregated_usage(aggregated_payload)

    assert [item.model for item in models] == [
        "claude-4.6-sonnet",
        "composer-2",
        "auto",
    ]
    assert models[0].input_tokens == 100
    assert models[0].output_tokens == 200
    assert models[0].cache_read_tokens == 50
    assert models[0].cache_write_tokens == 25
    assert models[0].total_cents == 12.5
    assert models[0].total_usd == 0.125
    assert models[0].total_tokens == 375
    assert totals["total_cost_cents"] == 13.75
    assert totals["total_input_tokens"] == 115
    assert totals["total_output_tokens"] == 225


def test_parse_aggregated_usage_skips_bad_rows() -> None:
    """Rows without a model name are ignored."""
    models, totals = parse_aggregated_usage(
        {
            "aggregations": [
                {"inputTokens": 1},
                "not-a-dict",
                {"modelIntent": "composer-2", "totalCents": "2.5"},
            ],
            "totalCostCents": None,
        }
    )

    assert len(models) == 1
    assert models[0].model == "composer-2"
    assert models[0].total_cents == 2.5
    assert totals["total_cost_cents"] is None


def test_iso_to_epoch_ms() -> None:
    """Billing-cycle timestamps convert to epoch milliseconds."""
    from datetime import datetime, timezone

    assert _iso_to_epoch_ms(None) is None
    assert _iso_to_epoch_ms("not-a-date") is None

    ms = _iso_to_epoch_ms("2026-04-02T14:11:55.000Z")
    assert ms is not None
    parsed = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    assert parsed == datetime(2026, 4, 2, 14, 11, 55, tzinfo=timezone.utc)


def test_cookie_header_value_encodes_separator() -> None:
    """Bare :: in the session token is URL-encoded for the Cookie header."""
    assert _cookie_header_value(" user_01::jwt.token ") == "user_01%3A%3Ajwt.token"
    assert (
        _cookie_header_value("user_01%3A%3Ajwt.token") == "user_01%3A%3Ajwt.token"
    )
