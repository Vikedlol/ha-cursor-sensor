"""Tests that auth failures become ConfigEntryAuthFailed for the reauth wizard.

Home Assistant is not installed in this repo's unit-test environment, so the
HA imports used by the coordinator are stubbed before import.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from cursor_usage.api import CursorApiError, CursorAuthError


def _install_ha_stubs() -> type[Exception]:
    """Install minimal homeassistant stubs and return ConfigEntryAuthFailed."""

    class ConfigEntryAuthFailed(Exception):
        """Stub of homeassistant.exceptions.ConfigEntryAuthFailed."""

    class UpdateFailed(Exception):
        """Stub of homeassistant.helpers.update_coordinator.UpdateFailed."""

    class DataUpdateCoordinator:
        """Minimal coordinator base that records init kwargs."""

        def __init__(self, hass, logger, *, name, update_interval) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval

        def __class_getitem__(cls, _item):
            return cls

    ha = types.ModuleType("homeassistant")
    ha_core = types.ModuleType("homeassistant.core")
    ha_core.HomeAssistant = object
    ha_exceptions = types.ModuleType("homeassistant.exceptions")
    ha_exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    ha_helpers = types.ModuleType("homeassistant.helpers")
    ha_helpers_uc = types.ModuleType("homeassistant.helpers.update_coordinator")
    ha_helpers_uc.DataUpdateCoordinator = DataUpdateCoordinator
    ha_helpers_uc.UpdateFailed = UpdateFailed

    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.core"] = ha_core
    sys.modules["homeassistant.exceptions"] = ha_exceptions
    sys.modules["homeassistant.helpers"] = ha_helpers
    sys.modules["homeassistant.helpers.update_coordinator"] = ha_helpers_uc
    return ConfigEntryAuthFailed


@pytest.fixture
def coordinator_module(monkeypatch: pytest.MonkeyPatch):
    """Import coordinator against stubbed Home Assistant modules."""
    for name in list(sys.modules):
        if name == "homeassistant" or name.startswith("homeassistant."):
            monkeypatch.delitem(sys.modules, name, raising=False)
        if name == "cursor_usage.coordinator":
            monkeypatch.delitem(sys.modules, name, raising=False)

    auth_failed_cls = _install_ha_stubs()
    from cursor_usage.coordinator import CursorUsageCoordinator

    return CursorUsageCoordinator, auth_failed_cls


async def test_auth_error_raises_config_entry_auth_failed(coordinator_module) -> None:
    """CursorAuthError must start reauth, not a silent unavailable/retry loop."""
    CursorUsageCoordinator, ConfigEntryAuthFailed = coordinator_module
    client = MagicMock()
    client.async_get_usage = AsyncMock(
        side_effect=CursorAuthError("Authentication failed (HTTP 401)")
    )
    coordinator = CursorUsageCoordinator(MagicMock(), client)

    with pytest.raises(ConfigEntryAuthFailed, match="invalid or expired"):
        await coordinator._async_update_data()


async def test_api_error_raises_update_failed(coordinator_module) -> None:
    """Transient API errors stay as UpdateFailed so polling retries."""
    CursorUsageCoordinator, _ConfigEntryAuthFailed = coordinator_module
    from homeassistant.helpers.update_coordinator import UpdateFailed

    client = MagicMock()
    client.async_get_usage = AsyncMock(side_effect=CursorApiError("HTTP error: 500"))
    coordinator = CursorUsageCoordinator(MagicMock(), client)

    with pytest.raises(UpdateFailed, match="Cursor API error"):
        await coordinator._async_update_data()
