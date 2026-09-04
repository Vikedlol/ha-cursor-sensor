"""Sensor platform for Cursor Usage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CursorUsageData, ModelUsage
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
    ATTR_MODEL,
    ATTR_MODELS,
    ATTR_OUTPUT_TOKENS,
    ATTR_REMAINING,
    ATTR_TOTAL_CENTS,
    ATTR_USED,
    CONF_NAME,
    DOMAIN,
)
from .coordinator import CursorUsageCoordinator

_MODEL_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, kw_only=True)
class CursorSensorEntityDescription(SensorEntityDescription):
    """Describe a Cursor usage sensor."""

    value_fn: Callable[[CursorUsageData], float | None]
    attrs_fn: Callable[[CursorUsageData], dict[str, Any]]


def _slugify_model(model: str) -> str:
    """Create a stable unique_id fragment from a model name."""
    slug = _MODEL_SLUG_RE.sub("_", model.lower()).strip("_")
    return slug or "unknown"


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
    """Attributes for the models overview sensor."""
    breakdown = {
        item.model: {
            ATTR_TOTAL_CENTS: item.total_cents,
            "total_usd": item.total_usd,
            ATTR_INPUT_TOKENS: item.input_tokens,
            ATTR_OUTPUT_TOKENS: item.output_tokens,
            ATTR_CACHE_READ_TOKENS: item.cache_read_tokens,
            ATTR_CACHE_WRITE_TOKENS: item.cache_write_tokens,
        }
        for item in data.models
    }
    return {
        **_common_attrs(data),
        ATTR_MODELS: breakdown,
        ATTR_INPUT_TOKENS: data.total_input_tokens,
        ATTR_OUTPUT_TOKENS: data.total_output_tokens,
        ATTR_CACHE_READ_TOKENS: data.total_cache_read_tokens,
        ATTR_CACHE_WRITE_TOKENS: data.total_cache_write_tokens,
        ATTR_TOTAL_CENTS: data.total_cost_cents,
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


SENSORS: tuple[CursorSensorEntityDescription, ...] = (
    CursorSensorEntityDescription(
        key="plan_percent",
        translation_key="plan_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.plan.total_percent_used,
        attrs_fn=_plan_attrs,
    ),
    CursorSensorEntityDescription(
        key="plan_used",
        translation_key="plan_used",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.plan.used,
        attrs_fn=_plan_attrs,
    ),
    CursorSensorEntityDescription(
        key="on_demand",
        translation_key="on_demand",
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
        native_unit_of_measurement="USD",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_models_total_usd,
        attrs_fn=_models_attrs,
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
    known_models: set[str] = set()

    async_add_entities(
        CursorUsageSensor(coordinator, entry, description, name)
        for description in SENSORS
    )

    @callback
    def _async_add_model_sensors() -> None:
        """Create a spend sensor for each newly seen model."""
        if not coordinator.data:
            return

        new_entities: list[CursorModelSpendSensor] = []
        for model_usage in coordinator.data.models:
            if model_usage.model in known_models:
                continue
            known_models.add(model_usage.model)
            new_entities.append(
                CursorModelSpendSensor(coordinator, entry, name, model_usage.model)
            )

        if new_entities:
            async_add_entities(new_entities)

    _async_add_model_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_model_sensors))


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


class CursorModelSpendSensor(
    CoordinatorEntity[CursorUsageCoordinator], SensorEntity
):
    """Per-model spend sensor for the current billing cycle."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "USD"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_translation_key = "model_spend"

    def __init__(
        self,
        coordinator: CursorUsageCoordinator,
        entry: ConfigEntry,
        device_name: str,
        model: str,
    ) -> None:
        """Initialize a model spend sensor."""
        super().__init__(coordinator)
        self._model = model
        self._attr_unique_id = f"{entry.entry_id}_model_{_slugify_model(model)}"
        self._attr_translation_placeholders = {"model": model}
        self._attr_name = model
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=device_name,
            manufacturer="Cursor",
            model="Usage",
        )

    def _model_usage(self) -> ModelUsage | None:
        """Find this model's row in the latest coordinator data."""
        if not self.coordinator.data:
            return None
        for item in self.coordinator.data.models:
            if item.model == self._model:
                return item
        return None

    @property
    def native_value(self) -> float | None:
        """Return model cost in USD for the billing cycle."""
        usage = self._model_usage()
        return usage.total_usd if usage else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return token and cost attributes for this model."""
        data = self.coordinator.data
        usage = self._model_usage()
        attrs = _common_attrs(data) if data else {}
        attrs[ATTR_MODEL] = self._model
        if usage is None:
            return attrs
        attrs.update(
            {
                ATTR_TOTAL_CENTS: usage.total_cents,
                ATTR_INPUT_TOKENS: usage.input_tokens,
                ATTR_OUTPUT_TOKENS: usage.output_tokens,
                ATTR_CACHE_READ_TOKENS: usage.cache_read_tokens,
                ATTR_CACHE_WRITE_TOKENS: usage.cache_write_tokens,
                "total_tokens": usage.total_tokens,
            }
        )
        return attrs
