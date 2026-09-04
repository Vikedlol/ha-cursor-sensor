#!/usr/bin/env python3
"""Fetch Cursor usage locally (no Home Assistant required).

Usage:
  set CURSOR_SESSION_TOKEN=...   # WorkosCursorSessionToken cookie value
  python scripts/fetch_usage.py
  python scripts/fetch_usage.py --token "user_01::jwt..." --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

from aiohttp import ClientSession  # noqa: E402

from cursor_usage.api import (  # noqa: E402
    CursorApiClient,
    CursorApiError,
    CursorAuthError,
    CursorUsageData,
)


def _format_usd(cents: float | None) -> str:
    if cents is None:
        return "n/a"
    return f"${cents / 100.0:.4f}"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def _format_millions(tokens: int | float) -> str:
    return f"{tokens / 1_000_000.0:.2f}M"


def _format_projection(label: str, projection) -> None:
    if projection is None:
        print(f"{label:<18}n/a")
        return
    projected = (
        f"{projection.projected_end_percent:.1f}%"
        if projection.projected_end_percent is not None
        else "n/a"
    )
    if projection.days_to_limit is None:
        eta = "n/a (no burn yet)"
    elif projection.within_cycle is False:
        eta = (
            f"after cycle ({projection.days_to_limit:.1f}d @ current rate; "
            f"eta {projection.eta.date() if projection.eta else 'n/a'})"
        )
    elif projection.percent_used >= 100:
        eta = "already at/over limit"
    else:
        eta = (
            f"{projection.days_to_limit:.1f}d "
            f"({projection.eta.date() if projection.eta else 'n/a'})"
        )
    print(
        f"{label:<18}{projected} at cycle end "
        f"(elapsed {projection.cycle_elapsed_percent:.1f}%, "
        f"{projection.cycle_days_remaining:.1f}d left; ETA 100%: {eta})"
    )


def _print_human(data: CursorUsageData) -> None:
    print(f"Membership:       {data.membership_type or 'n/a'}")
    print(f"Billing cycle:    {data.billing_cycle_start} → {data.billing_cycle_end}")
    # Dashboard "Included in Pro" bars:
    # autoPercentUsed ≈ Cursor Models, apiPercentUsed ≈ Other Models.
    print(f"Cursor Models:    {_format_percent(data.plan.auto_percent_used)}")
    print(f"Other Models:     {_format_percent(data.plan.api_percent_used)}")
    print(f"Total (API):      {_format_percent(data.plan.total_percent_used)}")
    _format_projection("Cursor projected:", data.project_cursor_models())
    _format_projection("Total projected:", data.project_total_usage())
    print(
        "Plan accounting:  "
        f"{data.plan.used}/{data.plan.limit} remaining {data.plan.remaining} "
        "(internal legacy fields; not the dashboard % bars)"
    )
    on_demand = (
        _format_usd(data.on_demand.used)
        if data.on_demand.enabled
        else "disabled"
    )
    print(f"On-demand:        {on_demand}")
    print(f"Models cost:      {_format_usd(data.total_cost_cents)}")
    print(
        f"Tokens used:      {_format_millions(data.total_tokens)} "
        f"(in={_format_millions(data.total_input_tokens)} "
        f"out={_format_millions(data.total_output_tokens)} "
        f"cache_r={_format_millions(data.total_cache_read_tokens)} "
        f"cache_w={_format_millions(data.total_cache_write_tokens)}; "
        f"raw={data.total_tokens:,})"
    )
    if not data.models:
        print("Models:           (none)")
        return
    print("Models:")
    for item in data.models:
        print(
            f"  - {item.model}: {_format_usd(item.total_cents)} / "
            f"{_format_millions(item.total_tokens)} "
            f"(in={_format_millions(item.input_tokens)} "
            f"out={_format_millions(item.output_tokens)} "
            f"cache_r={_format_millions(item.cache_read_tokens)} "
            f"cache_w={_format_millions(item.cache_write_tokens)})"
        )


# Avoid double projection calls in JSON output
def _to_dict(data: CursorUsageData) -> dict:
    cursor_proj = data.project_cursor_models()
    total_proj = data.project_total_usage()
    return {
        "membership_type": data.membership_type,
        "billing_cycle_start": data.billing_cycle_start,
        "billing_cycle_end": data.billing_cycle_end,
        "plan": {
            "enabled": data.plan.enabled,
            "used": data.plan.used,
            "limit": data.plan.limit,
            "remaining": data.plan.remaining,
            "cursor_models_percent": data.plan.auto_percent_used,
            "other_models_percent": data.plan.api_percent_used,
            "total_percent_used": data.plan.total_percent_used,
            "api_percent_used": data.plan.api_percent_used,
            "auto_percent_used": data.plan.auto_percent_used,
        },
        "projections": {
            "cursor_models": cursor_proj.as_dict() if cursor_proj else None,
            "total_usage": total_proj.as_dict() if total_proj else None,
        },
        "on_demand": {
            "enabled": data.on_demand.enabled,
            "used_cents": data.on_demand.used,
            "limit": data.on_demand.limit,
            "remaining": data.on_demand.remaining,
        },
        "total_cost_cents": data.total_cost_cents,
        "total_tokens": data.total_tokens,
        "total_tokens_millions": round(data.total_tokens / 1_000_000.0, 4),
        "total_input_tokens": data.total_input_tokens,
        "total_output_tokens": data.total_output_tokens,
        "total_cache_read_tokens": data.total_cache_read_tokens,
        "total_cache_write_tokens": data.total_cache_write_tokens,
        "models": [
            {
                "model": item.model,
                "total_cents": item.total_cents,
                "total_usd": item.total_usd,
                "total_tokens": item.total_tokens,
                "total_tokens_millions": round(item.total_tokens / 1_000_000.0, 4),
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
                "cache_read_tokens": item.cache_read_tokens,
                "cache_write_tokens": item.cache_write_tokens,
            }
            for item in data.models
        ],
    }


async def _run(token: str) -> CursorUsageData:
    async with ClientSession() as session:
        client = CursorApiClient(session, token)
        return await client.async_get_usage()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Cursor personal usage via the dashboard session cookie."
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("CURSOR_SESSION_TOKEN", ""),
        help="WorkosCursorSessionToken value (or set CURSOR_SESSION_TOKEN)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a summary",
    )
    args = parser.parse_args(argv)

    if not args.token.strip():
        parser.error(
            "Pass --token or set CURSOR_SESSION_TOKEN to your "
            "WorkosCursorSessionToken cookie value"
        )

    try:
        data = asyncio.run(_run(args.token))
    except CursorAuthError as err:
        print(f"Auth error: {err}", file=sys.stderr)
        return 1
    except CursorApiError as err:
        print(f"API error: {err}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(_to_dict(data), indent=2))
    else:
        _print_human(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
