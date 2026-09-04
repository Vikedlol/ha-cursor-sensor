"""Tests for CursorApiClient HTTP behavior (mocked aiohttp session)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cursor_usage.api import CursorApiClient, CursorAuthError


class _FakeResponse:
    """Minimal async context-manager response."""

    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status >= 400:
            from aiohttp import ClientResponseError

            raise ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=self.status,
            )

    async def json(self, content_type: str | None = None) -> Any:
        return self._payload


def _session_with_routes(routes: dict[tuple[str, str], _FakeResponse]) -> MagicMock:
    """Build a session.request mock that dispatches by method+url suffix."""

    def _request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        for (route_method, suffix), response in routes.items():
            if method == route_method and url.endswith(suffix):
                return response
        raise AssertionError(f"Unexpected request {method} {url}")

    session = MagicMock()
    session.request = MagicMock(side_effect=_request)
    return session


async def test_async_get_usage_merges_summary_and_models() -> None:
    """Client merges usage-summary with aggregated model rows."""
    session = _session_with_routes(
        {
            ("GET", "/api/usage-summary"): _FakeResponse(
                200,
                {
                    "billingCycleStart": "2026-04-02T14:11:55.000Z",
                    "billingCycleEnd": "2026-05-02T14:11:55.000Z",
                    "membershipType": "pro",
                    "individualUsage": {
                        "plan": {
                            "enabled": True,
                            "used": 10,
                            "limit": 100,
                            "remaining": 90,
                            "totalPercentUsed": 10,
                        },
                        "onDemand": {"enabled": False, "used": 0},
                    },
                },
            ),
            ("GET", "/api/auth/me"): _FakeResponse(
                200, {"id": 42, "email": "dev@example.com"}
            ),
            ("POST", "/api/dashboard/get-aggregated-usage-events"): _FakeResponse(
                200,
                {
                    "aggregations": [
                        {
                            "modelIntent": "composer-2",
                            "inputTokens": "1",
                            "outputTokens": "2",
                            "totalCents": 3.0,
                        }
                    ],
                    "totalCostCents": 3.0,
                    "totalInputTokens": "1",
                    "totalOutputTokens": "2",
                    "totalCacheReadTokens": "0",
                    "totalCacheWriteTokens": "0",
                },
            ),
        }
    )

    client = CursorApiClient(session, "user_01::test-token")
    data = await client.async_get_usage()

    assert data.membership_type == "pro"
    assert data.plan.used == 10
    assert len(data.models) == 1
    assert data.models[0].model == "composer-2"
    assert data.models[0].total_usd == 0.03
    assert data.total_cost_cents == 3.0

    # Cookie should encode :: and Origin must be present on requests.
    _args, kwargs = session.request.call_args_list[0]
    assert "user_01%3A%3Atest-token" in kwargs["headers"]["Cookie"]
    assert kwargs["headers"]["Origin"] == "https://cursor.com"


async def test_async_get_usage_summary_auth_error() -> None:
    """401 from usage-summary becomes CursorAuthError."""
    session = _session_with_routes(
        {
            ("GET", "/api/usage-summary"): _FakeResponse(
                401, {"error": "not_authenticated"}
            ),
        }
    )
    client = CursorApiClient(session, "bad-token")

    with pytest.raises(CursorAuthError):
        await client.async_get_usage_summary()


async def test_empty_token_raises() -> None:
    """Blank session token fails before any network call."""
    session = MagicMock()
    session.request = AsyncMock()
    client = CursorApiClient(session, "   ")

    with pytest.raises(CursorAuthError):
        await client.async_get_usage_summary()
    session.request.assert_not_called()
