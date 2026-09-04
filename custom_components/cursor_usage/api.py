"""API client for Cursor dashboard usage endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout

from .const import COOKIE_NAME, ORIGIN_HEADER, USAGE_SUMMARY_URL

_REQUEST_TIMEOUT = ClientTimeout(total=30)


class CursorApiError(Exception):
    """Base error for Cursor API failures."""


class CursorAuthError(CursorApiError):
    """Raised when the session token is missing or rejected."""


@dataclass(slots=True)
class PlanUsage:
    """Plan allowance usage for the current billing cycle."""

    enabled: bool
    used: float | None
    limit: float | None
    remaining: float | None
    auto_percent_used: float | None
    api_percent_used: float | None
    total_percent_used: float | None


@dataclass(slots=True)
class OnDemandUsage:
    """On-demand (usage-based) spend for the current billing cycle."""

    enabled: bool
    used: float | None
    limit: float | None
    remaining: float | None


@dataclass(slots=True)
class CursorUsageData:
    """Normalized usage summary from the dashboard API."""

    billing_cycle_start: str | None
    billing_cycle_end: str | None
    membership_type: str | None
    plan: PlanUsage
    on_demand: OnDemandUsage


def _as_float(value: Any) -> float | None:
    """Convert a numeric API field to float, or None if missing/invalid."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_bucket(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Return a dict for a usage bucket, defaulting to empty."""
    return raw if isinstance(raw, dict) else {}


def parse_usage_summary(payload: dict[str, Any]) -> CursorUsageData:
    """Parse a usage-summary JSON body into typed data."""
    individual = payload.get("individualUsage")
    if not isinstance(individual, dict):
        individual = {}

    plan_raw = _parse_bucket(individual.get("plan"))
    on_demand_raw = _parse_bucket(individual.get("onDemand"))

    plan = PlanUsage(
        enabled=bool(plan_raw.get("enabled", False)),
        used=_as_float(plan_raw.get("used")),
        limit=_as_float(plan_raw.get("limit")),
        remaining=_as_float(plan_raw.get("remaining")),
        auto_percent_used=_as_float(plan_raw.get("autoPercentUsed")),
        api_percent_used=_as_float(plan_raw.get("apiPercentUsed")),
        total_percent_used=_as_float(plan_raw.get("totalPercentUsed")),
    )
    on_demand = OnDemandUsage(
        enabled=bool(on_demand_raw.get("enabled", False)),
        used=_as_float(on_demand_raw.get("used")),
        limit=_as_float(on_demand_raw.get("limit")),
        remaining=_as_float(on_demand_raw.get("remaining")),
    )

    return CursorUsageData(
        billing_cycle_start=payload.get("billingCycleStart"),
        billing_cycle_end=payload.get("billingCycleEnd"),
        membership_type=payload.get("membershipType"),
        plan=plan,
        on_demand=on_demand,
    )


class CursorApiClient:
    """HTTP client for Cursor personal usage summary."""

    def __init__(self, session: ClientSession, session_token: str) -> None:
        """Initialize with an aiohttp session and WorkOS cookie value."""
        self._session = session
        self._session_token = session_token.strip()

    async def async_get_usage_summary(self) -> CursorUsageData:
        """Fetch and parse GET /api/usage-summary."""
        if not self._session_token:
            raise CursorAuthError("Session token is empty")

        headers = {
            "Cookie": f"{COOKIE_NAME}={self._session_token}",
            "Origin": ORIGIN_HEADER,
            "Accept": "application/json",
        }

        try:
            async with self._session.get(
                USAGE_SUMMARY_URL,
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            ) as response:
                if response.status in (401, 403):
                    raise CursorAuthError(
                        f"Authentication failed (HTTP {response.status})"
                    )
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except CursorAuthError:
            raise
        except ClientResponseError as err:
            raise CursorApiError(f"HTTP error: {err.status}") from err
        except (ClientError, TimeoutError) as err:
            raise CursorApiError(f"Request failed: {err}") from err
        except ValueError as err:
            raise CursorApiError(f"Invalid JSON response: {err}") from err

        if not isinstance(payload, dict):
            raise CursorApiError("Unexpected usage-summary payload")

        if payload.get("error") == "not_authenticated":
            raise CursorAuthError("Session token rejected by Cursor")

        return parse_usage_summary(payload)
