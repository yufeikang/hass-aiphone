"""Camera: snapshot from the latest captured mp4 (passive ring or monitor)."""
from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_CAMERA_REFRESH
from .coordinator import AiphoneCoordinator

# When a passive capture is in progress but no live frame has been decoded
# yet, wait briefly polling for one. Empirically: track event arrives ~0.2s,
# DTLS + first H.264 keyframe decoded usually 1-3s. We poll up to this
# limit so an automation that fetches the snapshot right after a ring gets
# the *current* visitor rather than a cached frame from the previous call.
LIVE_FRAME_WAIT_TIMEOUT_S = 4.5
LIVE_FRAME_POLL_INTERVAL_S = 0.15

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: AiphoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AiphoneEntranceCamera(coord)])


class AiphoneEntranceCamera(Camera):
    _attr_has_entity_name = True
    _attr_name = "Entrance"
    _attr_icon = "mdi:doorbell-video"

    def __init__(self, coordinator: AiphoneCoordinator) -> None:
        super().__init__()
        self._coord = coordinator
        self._attr_unique_id = f"{coordinator.device_id}_entrance"
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
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CAMERA_REFRESH, self._on_refresh)
        )

    @callback
    def _on_refresh(self) -> None:
        # Invalidate the cached frame; next snapshot read picks up the new mp4.
        self._cached_path = None
        self._cached_jpeg = None
        self.async_write_ha_state()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        # Live frame from an in-progress capture beats decoding the previous
        # mp4. As soon as the first video frame of a new call arrives, this
        # path returns the current visitor; before that, fall through to the
        # newest finalized recording so the entity is never blank.
        live = await self._coord.video.async_live_jpeg()
        if live is not None:
            return live
        # If a passive capture is in progress, the first decoded frame may not
        # have arrived yet (DTLS + first keyframe takes 1-3s). Wait briefly
        # so that an automation reading entity_picture right after a ring
        # returns the CURRENT visitor instead of a stale mp4 cache hit.
        video = self._coord.video
        if getattr(video, "_passive_pc", None) is not None:
            deadline = asyncio.get_event_loop().time() + LIVE_FRAME_WAIT_TIMEOUT_S
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(LIVE_FRAME_POLL_INTERVAL_S)
                live = await video.async_live_jpeg()
                if live is not None:
                    _LOGGER.debug("async_camera_image: got live frame after wait")
                    return live
        rec_dir = self._coord.video.recordings_dir
        result = await self.hass.async_add_executor_job(
            _pick_and_extract, rec_dir, self._cached_path
        )
        if result is None:
            return None
        latest, jpeg = result
        if jpeg is not None:
            self._cached_path = latest
            self._cached_jpeg = jpeg
        return self._cached_jpeg


def _pick_and_extract(
    rec_dir: Path,
    cached_path: Path | None,
) -> tuple[Path, bytes | None] | None:
    """Find the newest mp4 and decode it; runs in executor (blocking IO + decode)."""
    try:
        files = sorted(rec_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return None
    if not files:
        return None
    latest = files[-1]
    if latest == cached_path:
        return latest, None
    return latest, _extract_jpeg(latest)


def _extract_jpeg(path: Path) -> bytes | None:
    """Decode the first key-frame of `path` and return a JPEG."""
    try:
        import av  # PyAV — declared in manifest requirements
    except ImportError:
        _LOGGER.warning("PyAV not available; camera snapshot disabled")
        return None
    try:
        with av.open(str(path)) as container:
            stream = next(
                (s for s in container.streams if s.type == "video"), None
            )
            if stream is None:
                return None
            stream.codec_context.skip_frame = "NONKEY"
            for frame in container.decode(stream):
                img = frame.to_image()
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=80)
                return buf.getvalue()
    except Exception:
        _LOGGER.exception("snapshot extraction failed for %s", path)
    return None
