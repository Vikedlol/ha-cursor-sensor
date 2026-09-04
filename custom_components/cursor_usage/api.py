"""API client for Cursor dashboard usage endpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout

from .const import (
    AGGREGATED_USAGE_URL,
    AUTH_ME_URL,
    COOKIE_NAME,
    ORIGIN_HEADER,
    USAGE_SUMMARY_URL,
)

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
class ModelUsage:
    """Per-model aggregated usage for the current billing cycle."""

    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_cents: float | None

    @property
    def total_usd(self) -> float | None:
        """Cost in USD, if cents are available."""
        if self.total_cents is None:
            return None
        return round(self.total_cents / 100.0, 4)

    @property
    def total_tokens(self) -> int:
        """Sum of input, output, and cache tokens."""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


@dataclass(slots=True)
class UsageProjection:
    """Linear burn-rate projection for a usage percentage vs the billing cycle."""

    percent_used: float
    cycle_elapsed_percent: float
    cycle_days_elapsed: float
    cycle_days_remaining: float
    cycle_days_total: float
    projected_end_percent: float | None
    days_to_limit: float | None
    eta: datetime | None
    within_cycle: bool | None

    def as_dict(self) -> dict[str, Any]:
        """Serialize for sensor attributes / JSON output."""
        return {
            "percent_used": round(self.percent_used, 4),
            "cycle_elapsed_percent": round(self.cycle_elapsed_percent, 4),
            "cycle_days_elapsed": round(self.cycle_days_elapsed, 4),
            "cycle_days_remaining": round(self.cycle_days_remaining, 4),
            "cycle_days_total": round(self.cycle_days_total, 4),
            "projected_end_percent": (
                round(self.projected_end_percent, 2)
                if self.projected_end_percent is not None
                else None
            ),
            "days_to_limit": (
                round(self.days_to_limit, 2) if self.days_to_limit is not None else None
            ),
            "eta": self.eta.isoformat() if self.eta is not None else None,
            "within_cycle": self.within_cycle,
        }


@dataclass(slots=True)
class CursorUsageData:
    """Normalized usage summary from the dashboard API."""

    billing_cycle_start: str | None
    billing_cycle_end: str | None
    membership_type: str | None
    plan: PlanUsage
    on_demand: OnDemandUsage
    models: list[ModelUsage] = field(default_factory=list)
    total_cost_cents: float | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Sum of all token categories for the billing cycle."""
        api_total = (
            self.total_input_tokens
            + self.total_output_tokens
            + self.total_cache_read_tokens
            + self.total_cache_write_tokens
        )
        if api_total:
            return api_total
        return sum(item.total_tokens for item in self.models)

    def project_cursor_models(
        self, *, now: datetime | None = None
    ) -> UsageProjection | None:
        """Project Cursor Models (auto) usage to the end of the billing cycle."""
        return project_percent_usage(
            self.plan.auto_percent_used,
            self.billing_cycle_start,
            self.billing_cycle_end,
            now=now,
        )

    def project_total_usage(
        self, *, now: datetime | None = None
    ) -> UsageProjection | None:
        """Project total plan usage percentage to the end of the billing cycle."""
        return project_percent_usage(
            self.plan.total_percent_used,
            self.billing_cycle_start,
            self.billing_cycle_end,
            now=now,
        )


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp into an aware UTC datetime."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def project_percent_usage(
    percent_used: float | None,
    cycle_start: str | None,
    cycle_end: str | None,
    *,
    now: datetime | None = None,
) -> UsageProjection | None:
    """Linearly project percent used across the billing cycle.

    Assumptions:
    - usage so far accrued at a constant average rate since cycle start
    - projected_end_percent = percent_used / cycle_elapsed_fraction
    - ETA is when that rate would hit 100%
    """
    if percent_used is None:
        return None

    start = _parse_iso_datetime(cycle_start)
    end = _parse_iso_datetime(cycle_end)
    if start is None or end is None or end <= start:
        return None

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)

    total_seconds = (end - start).total_seconds()
    elapsed_seconds = max(0.0, min((current - start).total_seconds(), total_seconds))
    remaining_seconds = max(0.0, total_seconds - elapsed_seconds)

    cycle_days_total = total_seconds / 86400.0
    cycle_days_elapsed = elapsed_seconds / 86400.0
    cycle_days_remaining = remaining_seconds / 86400.0
    cycle_elapsed_percent = (
        (elapsed_seconds / total_seconds) * 100.0 if total_seconds else 0.0
    )

    projected_end_percent: float | None = None
    days_to_limit: float | None = None
    eta: datetime | None = None
    within_cycle: bool | None = None

    if elapsed_seconds > 0:
        elapsed_fraction = elapsed_seconds / total_seconds
        projected_end_percent = percent_used / elapsed_fraction

        if percent_used <= 0:
            days_to_limit = None
            eta = None
            within_cycle = None
        elif percent_used >= 100:
            days_to_limit = 0.0
            eta = current
            within_cycle = current <= end
        else:
            # percent per day based on elapsed time
            rate_per_day = percent_used / cycle_days_elapsed
            if rate_per_day > 0:
                days_to_limit = (100.0 - percent_used) / rate_per_day
                eta = current + timedelta(days=days_to_limit)
                within_cycle = eta <= end

    return UsageProjection(
        percent_used=percent_used,
        cycle_elapsed_percent=cycle_elapsed_percent,
        cycle_days_elapsed=cycle_days_elapsed,
        cycle_days_remaining=cycle_days_remaining,
        cycle_days_total=cycle_days_total,
        projected_end_percent=projected_end_percent,
        days_to_limit=days_to_limit,
        eta=eta,
        within_cycle=within_cycle,
    )


def _as_float(value: Any) -> float | None:
    """Convert a numeric API field to float, or None if missing/invalid."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int:
    """Convert a numeric API field to int, defaulting to 0."""
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _parse_bucket(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Return a dict for a usage bucket, defaulting to empty."""
    return raw if isinstance(raw, dict) else {}


def _iso_to_epoch_ms(value: str | None) -> int | None:
    """Parse an ISO-8601 timestamp to epoch milliseconds."""
    if not value or not isinstance(value, str):
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def _cookie_header_value(session_token: str) -> str:
    """Build WorkosCursorSessionToken cookie value (encode bare ::)."""
    value = session_token.strip()
    if "::" in value and "%3A%3A" not in value.upper():
        value = value.replace("::", "%3A%3A", 1)
    return value


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


def parse_aggregated_usage(payload: dict[str, Any]) -> tuple[list[ModelUsage], dict[str, Any]]:
    """Parse aggregated usage events into model rows and totals."""
    aggregations = payload.get("aggregations")
    if not isinstance(aggregations, list):
        aggregations = []

    models: list[ModelUsage] = []
    for row in aggregations:
        if not isinstance(row, dict):
            continue
        model = row.get("modelIntent") or row.get("model") or row.get("modelName")
        if not model:
            continue
        models.append(
            ModelUsage(
                model=str(model),
                input_tokens=_as_int(row.get("inputTokens")),
                output_tokens=_as_int(row.get("outputTokens")),
                cache_read_tokens=_as_int(row.get("cacheReadTokens")),
                cache_write_tokens=_as_int(row.get("cacheWriteTokens")),
                total_cents=_as_float(row.get("totalCents")),
            )
        )

    models.sort(key=lambda item: (-(item.total_cents or 0.0), item.model.lower()))

    totals = {
        "total_cost_cents": _as_float(payload.get("totalCostCents")),
        "total_input_tokens": _as_int(payload.get("totalInputTokens")),
        "total_output_tokens": _as_int(payload.get("totalOutputTokens")),
        "total_cache_read_tokens": _as_int(payload.get("totalCacheReadTokens")),
        "total_cache_write_tokens": _as_int(payload.get("totalCacheWriteTokens")),
    }
    return models, totals


class CursorApiClient:
    """HTTP client for Cursor personal usage summary and model breakdown."""

    def __init__(self, session: ClientSession, session_token: str) -> None:
        """Initialize with an aiohttp session and WorkOS cookie value."""
        self._session = session
        self._session_token = session_token.strip()

    def _headers(self, *, with_json: bool) -> dict[str, str]:
        """Common request headers including session cookie."""
        headers = {
            "Cookie": f"{COOKIE_NAME}={_cookie_header_value(self._session_token)}",
            "Origin": ORIGIN_HEADER,
            "Accept": "application/json",
        }
        if with_json:
            headers["Content-Type"] = "application/json"
        return headers

    async def _request(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an authenticated JSON request against cursor.com."""
        if not self._session_token:
            raise CursorAuthError("Session token is empty")

        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(with_json=body is not None),
                json=body,
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
            raise CursorApiError(f"Unexpected payload from {url}")

        if payload.get("error") == "not_authenticated":
            raise CursorAuthError("Session token rejected by Cursor")

        return payload

    async def async_get_usage_summary(self) -> CursorUsageData:
        """Fetch GET /api/usage-summary only (used by config flow validation)."""
        payload = await self._request("GET", USAGE_SUMMARY_URL)
        return parse_usage_summary(payload)

    async def async_get_usage(self) -> CursorUsageData:
        """Fetch summary plus per-model aggregated usage for the billing cycle."""
        summary = await self.async_get_usage_summary()

        start_ms = _iso_to_epoch_ms(summary.billing_cycle_start)
        end_ms = _iso_to_epoch_ms(summary.billing_cycle_end)
        if start_ms is None or end_ms is None:
            return summary

        me = await self._request("GET", AUTH_ME_URL)
        user_id = me.get("id")
        if user_id is None:
            raise CursorApiError("auth/me response missing user id")

        aggregated = await self._request(
            "POST",
            AGGREGATED_USAGE_URL,
            {
                "teamId": 0,
                "startDate": str(start_ms),
                "endDate": str(end_ms),
                "userId": user_id,
            },
        )
        models, totals = parse_aggregated_usage(aggregated)
        summary.models = models
        summary.total_cost_cents = totals["total_cost_cents"]
        summary.total_input_tokens = totals["total_input_tokens"]
        summary.total_output_tokens = totals["total_output_tokens"]
        summary.total_cache_read_tokens = totals["total_cache_read_tokens"]
        summary.total_cache_write_tokens = totals["total_cache_write_tokens"]
        return summary
