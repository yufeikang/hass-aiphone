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

    Filesystem state is read off the event loop on first add and on every
    SIGNAL_CAMERA_REFRESH (= recording finalized); native_value /
    extra_state_attributes only return the cached values, so HA's frequent
    polling never hits the disk.
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
        self._cached_state: datetime | None = None
        self._cached_attrs: dict | None = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CAMERA_REFRESH, self._on_update)
        )
        # Seed cache from current filesystem state, off the event loop
        await self._async_refresh_and_write()

    @callback
    def _on_update(self) -> None:
        # SIGNAL_CAMERA_REFRESH fires after a recording finalized. Refresh the
        # cache (off-loop) THEN write_ha_state — the previous race wrote stale
        # values because async_add_executor_job is fire-and-forget.
        self.hass.async_create_task(self._async_refresh_and_write())

    async def _async_refresh_and_write(self) -> None:
        await self.hass.async_add_executor_job(self._refresh_cache_sync)
        self.async_write_ha_state()

    def _refresh_cache_sync(self) -> None:
        """Runs in executor — safe to do blocking glob/stat."""
        latest = self._coord.video.latest_recording
        if latest is None:
            self._cached_state = None
            self._cached_attrs = None
            return
        try:
            stat = latest.stat()
        except OSError:
            return
        self._cached_state = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        self._cached_attrs = {
            "file_path": str(latest),
            "file_name": latest.name,
            "size_bytes": stat.st_size,
            "kind": "monitor" if latest.name.startswith("monitor-") else "ring",
        }

    @property
    def native_value(self) -> datetime | None:
        return self._cached_state

    @property
    def extra_state_attributes(self) -> dict | None:
        return self._cached_attrs
