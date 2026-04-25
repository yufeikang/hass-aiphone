"""Lock: momentary electric strike on the WP-2MED's relay output (MID 26021)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AiphoneCoordinator

_LOGGER = logging.getLogger(__name__)

# WP-2MED's relay auto-relocks after ~3s; pad a little so HA's "unlocked"
# blip is visible to users without lying about the physical state.
RELOCK_AFTER_S = 5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: AiphoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AiphoneDoorLock(coord)])


class AiphoneDoorLock(LockEntity):
    _attr_has_entity_name = True
    _attr_name = "Door"
    _attr_icon = "mdi:door"
    _attr_should_poll = False

    def __init__(self, coordinator: AiphoneCoordinator) -> None:
        self._coord = coordinator
        self._attr_unique_id = f"{coordinator.device_id}_door_lock"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            connections={(CONNECTION_NETWORK_MAC, coordinator.device_mac)},
            name="Aiphone WP-2MED",
            manufacturer="Aiphone",
            model="WP-2MED",
        )
        self._is_locked = True
        self._is_unlocking = False
        self._relock_handle: asyncio.TimerHandle | None = None

    @property
    def is_locked(self) -> bool:
        return self._is_locked

    @property
    def is_unlocking(self) -> bool:
        return self._is_unlocking

    async def async_unlock(self, **kwargs: Any) -> None:
        self._coord.async_unlock_door()
        self._is_locked = False
        self._is_unlocking = True
        self.async_write_ha_state()
        if self._relock_handle is not None:
            self._relock_handle.cancel()
        self._relock_handle = self.hass.loop.call_later(
            RELOCK_AFTER_S, self._on_relock
        )

    async def async_lock(self, **kwargs: Any) -> None:
        # The unit auto-relocks; a manual lock command just clears HA's
        # transient unlocked state.
        if self._relock_handle is not None:
            self._relock_handle.cancel()
            self._relock_handle = None
        self._on_relock()

    def _on_relock(self) -> None:
        self._relock_handle = None
        self._is_locked = True
        self._is_unlocking = False
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._relock_handle is not None:
            self._relock_handle.cancel()
            self._relock_handle = None
