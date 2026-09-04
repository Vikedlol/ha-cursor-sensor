"""Shared fixtures for Cursor Usage tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def usage_summary_payload() -> dict:
    """Sample GET /api/usage-summary response."""
    return {
        "billingCycleStart": "2026-04-02T14:11:55.000Z",
        "billingCycleEnd": "2026-05-02T14:11:55.000Z",
        "membershipType": "pro",
        "individualUsage": {
            "plan": {
                "enabled": True,
                "used": 1500,
                "limit": 2000,
                "remaining": 500,
                "autoPercentUsed": 1.24,
                "apiPercentUsed": 3.0,
                "totalPercentUsed": 1.24,
            },
            "onDemand": {
                "enabled": True,
                "used": 2309,
                "limit": None,
                "remaining": None,
            },
        },
    }


@pytest.fixture
def aggregated_payload() -> dict:
    """Sample POST /api/dashboard/get-aggregated-usage-events response."""
    return {
        "aggregations": [
            {
                "modelIntent": "claude-4.6-sonnet",
                "inputTokens": "100",
                "outputTokens": "200",
                "cacheReadTokens": "50",
                "cacheWriteTokens": "25",
                "totalCents": 12.5,
            },
            {
                "modelIntent": "composer-2",
                "inputTokens": "10",
                "outputTokens": "20",
                "cacheReadTokens": "0",
                "cacheWriteTokens": "0",
                "totalCents": 1.0,
            },
            {
                "model": "auto",
                "inputTokens": "5",
                "outputTokens": "5",
                "totalCents": 0.25,
            },
        ],
        "totalInputTokens": "115",
        "totalOutputTokens": "225",
        "totalCacheReadTokens": "50",
        "totalCacheWriteTokens": "25",
        "totalCostCents": 13.75,
    }
