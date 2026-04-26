"""Image: last snapshot extracted from the most-recently finalized recording.

Distinct from `camera.aiphone_wp_2med_entrance` which serves a live frame
from in-progress captures (or the latest mp4 when idle). This entity is
specifically the still image of the last visitor — meant to be the
counterpart of `sensor.last_recording` for use in dashboards / automations.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from pathlib import Path

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_CAMERA_REFRESH
from .coordinator import AiphoneCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: AiphoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AiphoneLastSnapshot(hass, coord)])


class AiphoneLastSnapshot(ImageEntity):
    _attr_has_entity_name = True
    _attr_name = "Last snapshot"
    _attr_icon = "mdi:image"
    _attr_content_type = "image/jpeg"

    def __init__(self, hass: HomeAssistant, coordinator: AiphoneCoordinator) -> None:
        super().__init__(hass)
        self._coord = coordinator
        self._attr_unique_id = f"{coordinator.device_id}_last_snapshot"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            connections={(CONNECTION_NETWORK_MAC, coordinator.device_mac)},
            name="Aiphone WP-2MED",
            manufacturer="Aiphone",
            model="WP-2MED",
        )
        self._cached_path: Path | None = None
        self._cached_jpeg: bytes | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CAMERA_REFRESH, self._on_refresh)
        )
        # Seed image_last_updated from the existing latest recording (off the
        # event loop because it does a synchronous glob/stat).
        await self.hass.async_add_executor_job(self._refresh_image_last_updated_sync)
        self.async_write_ha_state()

    @callback
    def _on_refresh(self) -> None:
        # New recording was finalized — invalidate cache. The fs scan to update
        # image_last_updated runs off-loop.
        self._cached_path = None
        self._cached_jpeg = None
        self.hass.async_add_executor_job(self._refresh_image_last_updated_sync)
        self.async_write_ha_state()

    def _refresh_image_last_updated_sync(self) -> None:
        latest = self._coord.video.latest_recording
        if latest:
            try:
                self._attr_image_last_updated = datetime.fromtimestamp(
                    latest.stat().st_mtime, tz=timezone.utc
                )
            except OSError:
                pass

    async def async_image(self) -> bytes | None:
        latest = self._coord.video.latest_recording
        if latest is None:
            return None
        if self._cached_path == latest and self._cached_jpeg is not None:
            return self._cached_jpeg
        jpeg = await self.hass.async_add_executor_job(_extract_first_frame, latest)
        if jpeg:
            self._cached_path = latest
            self._cached_jpeg = jpeg
        return jpeg


def _extract_first_frame(mp4: Path) -> bytes | None:
    """Pull the first decodable video frame from `mp4` and return JPEG bytes."""
    try:
        import av  # PyAV — already a dependency via aiortc/MediaRecorder
    except ImportError:
        _LOGGER.error("PyAV not available — cannot decode mp4")
        return None
    try:
        with av.open(str(mp4)) as container:
            video = container.streams.video[0]
            for frame in container.decode(video):
                img = frame.to_image()
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                return buf.getvalue()
    except Exception as e:  # noqa: BLE001
        _LOGGER.warning("first-frame extract failed for %s: %s", mp4.name, e)
    return None
