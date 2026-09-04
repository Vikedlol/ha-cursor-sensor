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


def _print_human(data: CursorUsageData) -> None:
    print(f"Membership:     {data.membership_type or 'n/a'}")
    print(f"Billing cycle:  {data.billing_cycle_start} → {data.billing_cycle_end}")
    print(
        "Plan:           "
        f"{data.plan.used}/{data.plan.limit} "
        f"({data.plan.total_percent_used}% used, remaining {data.plan.remaining})"
    )
    on_demand = (
        _format_usd(data.on_demand.used)
        if data.on_demand.enabled
        else "disabled"
    )
    print(f"On-demand:      {on_demand}")
    print(f"Models cost:    {_format_usd(data.total_cost_cents)}")
    if not data.models:
        print("Models:         (none)")
        return
    print("Models:")
    for item in data.models:
        print(
            f"  - {item.model}: {_format_usd(item.total_cents)} "
            f"(in={item.input_tokens} out={item.output_tokens} "
            f"cache_r={item.cache_read_tokens} cache_w={item.cache_write_tokens})"
        )


def _to_dict(data: CursorUsageData) -> dict:
    return {
        "membership_type": data.membership_type,
        "billing_cycle_start": data.billing_cycle_start,
        "billing_cycle_end": data.billing_cycle_end,
        "plan": {
            "enabled": data.plan.enabled,
            "used": data.plan.used,
            "limit": data.plan.limit,
            "remaining": data.plan.remaining,
            "total_percent_used": data.plan.total_percent_used,
            "api_percent_used": data.plan.api_percent_used,
            "auto_percent_used": data.plan.auto_percent_used,
        },
        "on_demand": {
            "enabled": data.on_demand.enabled,
            "used_cents": data.on_demand.used,
            "limit": data.on_demand.limit,
            "remaining": data.on_demand.remaining,
        },
        "total_cost_cents": data.total_cost_cents,
        "models": [
            {
                "model": item.model,
                "total_cents": item.total_cents,
                "total_usd": item.total_usd,
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
