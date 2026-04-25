"""Sensors: last caller, doorbell state."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_STATE_UPDATE
from .coordinator import AiphoneCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: AiphoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AiphoneDoorbellState(coord),
            AiphoneLastCaller(coord),
        ]
    )


class _AiphoneSensorBase(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: AiphoneCoordinator) -> None:
        self._coord = coordinator
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            connections={(CONNECTION_NETWORK_MAC, coordinator.device_mac)},
            name="Aiphone WP-2MED",
            manufacturer="Aiphone",
            model="WP-2MED",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_STATE_UPDATE, self._on_update)
        )

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()


class AiphoneDoorbellState(_AiphoneSensorBase):
    _attr_name = "Doorbell state"
    _attr_icon = "mdi:doorbell-video"

    def __init__(self, coordinator: AiphoneCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_doorbell_state"

    @property
    def native_value(self) -> str:
        return self._coord.doorbell_state


class AiphoneLastCaller(_AiphoneSensorBase):
    _attr_name = "Last caller"
    _attr_icon = "mdi:account-voice"

    def __init__(self, coordinator: AiphoneCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_last_caller"

    @property
    def native_value(self) -> str:
        return self._coord.last_caller or ""
