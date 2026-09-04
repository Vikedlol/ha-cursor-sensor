"""Sensor platform for Cursor Usage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CursorUsageData, UsageProjection
from .const import (
    ATTR_API_PERCENT_USED,
    ATTR_AUTO_PERCENT_USED,
    ATTR_BILLING_CYCLE_END,
    ATTR_BILLING_CYCLE_START,
    ATTR_CACHE_READ_TOKENS,
    ATTR_CACHE_WRITE_TOKENS,
    ATTR_ENABLED,
    ATTR_INPUT_TOKENS,
    ATTR_LIMIT,
    ATTR_MEMBERSHIP_TYPE,
    ATTR_MODELS,
    ATTR_OUTPUT_TOKENS,
    ATTR_REMAINING,
    ATTR_TOTAL_CENTS,
    ATTR_USED,
    CONF_NAME,
    DOMAIN,
)
from .coordinator import CursorUsageCoordinator


@dataclass(frozen=True, kw_only=True)
class CursorSensorEntityDescription(SensorEntityDescription):
    """Describe a Cursor usage sensor."""

    value_fn: Callable[[CursorUsageData], float | None]
    attrs_fn: Callable[[CursorUsageData], dict[str, Any]]


def _projection_attrs(projection: UsageProjection | None) -> dict[str, Any]:
    """Flatten a usage projection into sensor attributes."""
    if projection is None:
        return {
            "projected_end_percent": None,
            "days_to_limit": None,
            "eta": None,
            "within_cycle": None,
            "cycle_elapsed_percent": None,
            "cycle_days_elapsed": None,
            "cycle_days_remaining": None,
            "cycle_days_total": None,
        }
    return projection.as_dict()


def _common_attrs(data: CursorUsageData) -> dict[str, Any]:
    """Attributes shared by all Cursor usage sensors."""
    return {
        ATTR_BILLING_CYCLE_START: data.billing_cycle_start,
        ATTR_BILLING_CYCLE_END: data.billing_cycle_end,
        ATTR_MEMBERSHIP_TYPE: data.membership_type,
    }


def _plan_attrs(data: CursorUsageData) -> dict[str, Any]:
    """Attributes for plan-related sensors."""
    return {
        **_common_attrs(data),
        ATTR_USED: data.plan.used,
        ATTR_LIMIT: data.plan.limit,
        ATTR_REMAINING: data.plan.remaining,
        ATTR_ENABLED: data.plan.enabled,
        ATTR_AUTO_PERCENT_USED: data.plan.auto_percent_used,
        ATTR_API_PERCENT_USED: data.plan.api_percent_used,
    }


def _cursor_models_attrs(data: CursorUsageData) -> dict[str, Any]:
    """Attributes for Cursor Models percent / projection sensors."""
    return {
        **_plan_attrs(data),
        **_projection_attrs(data.project_cursor_models()),
    }


def _total_usage_attrs(data: CursorUsageData) -> dict[str, Any]:
    """Attributes for total usage percent / projection sensors."""
    return {
        **_plan_attrs(data),
        **_projection_attrs(data.project_total_usage()),
    }


def _on_demand_attrs(data: CursorUsageData) -> dict[str, Any]:
    """Attributes for on-demand spend sensor."""
    used_cents = data.on_demand.used
    return {
        **_common_attrs(data),
        ATTR_USED: used_cents,
        ATTR_LIMIT: data.on_demand.limit,
        ATTR_REMAINING: data.on_demand.remaining,
        ATTR_ENABLED: data.on_demand.enabled,
        "used_usd": round(used_cents / 100.0, 4) if used_cents is not None else None,
    }


def _models_attrs(data: CursorUsageData) -> dict[str, Any]:
    """Attributes for the models cost sensor, including per-model breakdown."""
    breakdown = {
        item.model: {
            "total_usd": item.total_usd,
            ATTR_TOTAL_CENTS: item.total_cents,
            ATTR_INPUT_TOKENS: item.input_tokens,
            ATTR_OUTPUT_TOKENS: item.output_tokens,
            ATTR_CACHE_READ_TOKENS: item.cache_read_tokens,
            ATTR_CACHE_WRITE_TOKENS: item.cache_write_tokens,
            "total_tokens": item.total_tokens,
        }
        for item in data.models
    }
    model_costs = {
        item.model: item.total_usd for item in data.models if item.total_usd is not None
    }
    return {
        **_common_attrs(data),
        ATTR_MODELS: breakdown,
        "model_costs": model_costs,
        ATTR_INPUT_TOKENS: data.total_input_tokens,
        ATTR_OUTPUT_TOKENS: data.total_output_tokens,
        ATTR_CACHE_READ_TOKENS: data.total_cache_read_tokens,
        ATTR_CACHE_WRITE_TOKENS: data.total_cache_write_tokens,
        ATTR_TOTAL_CENTS: data.total_cost_cents,
        "total_tokens": data.total_tokens,
        "model_count": len(data.models),
    }


def _tokens_to_millions(value: int | float) -> float:
    """Convert a token count to millions."""
    return round(float(value) / 1_000_000.0, 4)


def _tokens_attrs(data: CursorUsageData) -> dict[str, Any]:
    """Attributes for the tokens used sensor (state is in millions)."""
    breakdown = {
        item.model: {
            "total_tokens_millions": _tokens_to_millions(item.total_tokens),
            "total_tokens": item.total_tokens,
            ATTR_INPUT_TOKENS: item.input_tokens,
            ATTR_OUTPUT_TOKENS: item.output_tokens,
            ATTR_CACHE_READ_TOKENS: item.cache_read_tokens,
            ATTR_CACHE_WRITE_TOKENS: item.cache_write_tokens,
        }
        for item in data.models
    }
    model_tokens = {
        item.model: _tokens_to_millions(item.total_tokens) for item in data.models
    }
    return {
        **_common_attrs(data),
        ATTR_MODELS: breakdown,
        "model_tokens": model_tokens,
        "total_tokens": data.total_tokens,
        ATTR_INPUT_TOKENS: data.total_input_tokens,
        ATTR_OUTPUT_TOKENS: data.total_output_tokens,
        ATTR_CACHE_READ_TOKENS: data.total_cache_read_tokens,
        ATTR_CACHE_WRITE_TOKENS: data.total_cache_write_tokens,
        "input_tokens_millions": _tokens_to_millions(data.total_input_tokens),
        "output_tokens_millions": _tokens_to_millions(data.total_output_tokens),
        "cache_read_tokens_millions": _tokens_to_millions(data.total_cache_read_tokens),
        "cache_write_tokens_millions": _tokens_to_millions(
            data.total_cache_write_tokens
        ),
        "model_count": len(data.models),
    }


def _models_total_usd(data: CursorUsageData) -> float | None:
    """Return aggregated model cost in USD."""
    if data.total_cost_cents is not None:
        return round(data.total_cost_cents / 100.0, 4)
    if not data.models:
        return None
    cents = sum(item.total_cents or 0.0 for item in data.models)
    return round(cents / 100.0, 4)


def _projected_end(projection: UsageProjection | None) -> float | None:
    """Return projected end-of-cycle percent, if available."""
    if projection is None or projection.projected_end_percent is None:
        return None
    return round(projection.projected_end_percent, 2)


SENSORS: tuple[CursorSensorEntityDescription, ...] = (
    CursorSensorEntityDescription(
        key="cursor_models_percent",
        translation_key="cursor_models_percent",
        icon="mdi:robot-outline",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: d.plan.auto_percent_used,
        attrs_fn=_cursor_models_attrs,
    ),
    CursorSensorEntityDescription(
        key="cursor_models_projected",
        translation_key="cursor_models_projected",
        icon="mdi:chart-timeline-variant",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: _projected_end(d.project_cursor_models()),
        attrs_fn=_cursor_models_attrs,
    ),
    CursorSensorEntityDescription(
        key="other_models_percent",
        translation_key="other_models_percent",
        icon="mdi:api",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: d.plan.api_percent_used,
        attrs_fn=_plan_attrs,
    ),
    CursorSensorEntityDescription(
        key="plan_percent",
        translation_key="plan_percent",
        icon="mdi:percent-outline",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: d.plan.total_percent_used,
        attrs_fn=_total_usage_attrs,
    ),
    CursorSensorEntityDescription(
        key="total_projected",
        translation_key="total_projected",
        icon="mdi:trending-up",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: _projected_end(d.project_total_usage()),
        attrs_fn=_total_usage_attrs,
    ),
    CursorSensorEntityDescription(
        key="plan_used",
        translation_key="plan_used",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.plan.used,
        attrs_fn=_plan_attrs,
        entity_registry_enabled_default=False,
    ),
    CursorSensorEntityDescription(
        key="on_demand",
        translation_key="on_demand",
        icon="mdi:cash-plus",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: (
            round(d.on_demand.used / 100.0, 4) if d.on_demand.used is not None else None
        ),
        attrs_fn=_on_demand_attrs,
    ),
    CursorSensorEntityDescription(
        key="models_cost",
        translation_key="models_cost",
        icon="mdi:currency-usd",
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_models_total_usd,
        attrs_fn=_models_attrs,
    ),
    CursorSensorEntityDescription(
        key="tokens_used",
        translation_key="tokens_used",
        icon="mdi:hexagon-multiple-outline",
        native_unit_of_measurement="M",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: _tokens_to_millions(d.total_tokens),
        attrs_fn=_tokens_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cursor Usage sensors from a config entry."""
    coordinator: CursorUsageCoordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME) or entry.title

    async_add_entities(
        CursorUsageSensor(coordinator, entry, description, name)
        for description in SENSORS
    )


class CursorUsageSensor(
    CoordinatorEntity[CursorUsageCoordinator], SensorEntity
):
    """Representation of a Cursor usage sensor."""

    entity_description: CursorSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CursorUsageCoordinator,
        entry: ConfigEntry,
        description: CursorSensorEntityDescription,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=device_name,
            manufacturer="Cursor",
            model="Usage",
        )

    @property
    def native_value(self) -> float | None:
        """Return the sensor state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes from the latest summary."""
        return self.entity_description.attrs_fn(self.coordinator.data)
