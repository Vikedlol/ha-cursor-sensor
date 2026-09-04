"""Data update coordinator for Cursor Usage."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CursorApiClient, CursorApiError, CursorAuthError, CursorUsageData
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class CursorUsageCoordinator(DataUpdateCoordinator[CursorUsageData]):
    """Coordinator that polls Cursor usage once per hour."""

    def __init__(self, hass: HomeAssistant, client: CursorApiClient) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> CursorUsageData:
        """Fetch usage summary and per-model aggregated spend."""
        try:
            return await self.client.async_get_usage()
        except CursorAuthError as err:
            raise UpdateFailed(f"Cursor authentication failed: {err}") from err
        except CursorApiError as err:
            raise UpdateFailed(f"Cursor API error: {err}") from err
