"""Tests for billing-cycle usage projections."""

from __future__ import annotations

from datetime import datetime, timezone

from cursor_usage.api import project_percent_usage


def test_project_percent_usage_mid_cycle() -> None:
    """Halfway through the cycle at 10% projects to 20% by end."""
    projection = project_percent_usage(
        10.0,
        "2026-09-01T00:00:00.000Z",
        "2026-10-01T00:00:00.000Z",
        now=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )

    assert projection is not None
    assert projection.cycle_days_total == 30.0
    assert abs(projection.cycle_elapsed_percent - 50.0) < 0.01
    assert abs(projection.projected_end_percent - 20.0) < 0.01
    assert projection.days_to_limit is not None
    assert projection.days_to_limit > projection.cycle_days_remaining
    assert projection.within_cycle is False


def test_project_percent_usage_will_hit_limit() -> None:
    """High burn rate yields an ETA inside the billing cycle."""
    projection = project_percent_usage(
        50.0,
        "2026-09-01T00:00:00.000Z",
        "2026-10-01T00:00:00.000Z",
        now=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )

    assert projection is not None
    assert projection.projected_end_percent is not None
    assert projection.projected_end_percent > 100
    assert projection.days_to_limit is not None
    assert projection.days_to_limit < projection.cycle_days_remaining
    assert projection.within_cycle is True
    assert projection.eta is not None


def test_project_percent_usage_zero_burn() -> None:
    """Zero usage has no ETA and projects to zero."""
    projection = project_percent_usage(
        0.0,
        "2026-09-01T00:00:00.000Z",
        "2026-10-01T00:00:00.000Z",
        now=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )

    assert projection is not None
    assert projection.projected_end_percent == 0.0
    assert projection.days_to_limit is None
    assert projection.eta is None


def test_project_percent_usage_missing_inputs() -> None:
    """Missing percent or cycle bounds returns None."""
    assert project_percent_usage(None, "2026-09-01T00:00:00Z", "2026-10-01T00:00:00Z") is None
    assert project_percent_usage(10.0, None, "2026-10-01T00:00:00Z") is None
