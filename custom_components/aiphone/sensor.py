"""Sensors: last caller, doorbell state, last recording."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_CAMERA_REFRESH, SIGNAL_STATE_UPDATE
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
            AiphoneLastRecording(coord),
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


class AiphoneLastRecording(SensorEntity):
    """Tracks the most recently finalized .mp4 in the recordings directory.

    state           = ISO timestamp the recording finalized at (timestamp class
                      so HA can render it as relative time / duration-since)
    attr.file_path  = absolute path to the mp4
    attr.file_name  = basename
    attr.size_bytes = file size
    attr.kind       = "ring" (passive, doorbell press) or "monitor" (active)
    """
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "Last recording"
    _attr_icon = "mdi:movie-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: AiphoneCoordinator) -> None:
        self._coord = coordinator
        self._attr_unique_id = f"{coordinator.device_id}_last_recording"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            connections={(CONNECTION_NETWORK_MAC, coordinator.device_mac)},
            name="Aiphone WP-2MED",
            manufacturer="Aiphone",
            model="WP-2MED",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CAMERA_REFRESH, self._on_update)
        )

    @callback
    def _on_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> datetime | None:
        latest = self._coord.video.latest_recording
        if latest is None:
            return None
        try:
            return datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return None

    @property
    def extra_state_attributes(self) -> dict | None:
        latest = self._coord.video.latest_recording
        if latest is None:
            return None
        try:
            stat = latest.stat()
        except OSError:
            return None
        kind = "monitor" if latest.name.startswith("monitor-") else "ring"
        return {
            "file_path": str(latest),
            "file_name": latest.name,
            "size_bytes": stat.st_size,
            "kind": kind,
        }
