"""WebRTC media capture for Aiphone — passive (doorbell ring) + active (monitor).

Two-PC architecture for active monitor (per CallManager.getMonitorRequests):
  PC #1 publisher placeholder  — claims our slot in the Janus VideoRoom
  PC #2 subscriber to WP-2MED  — actually receives the camera feed

Passive doorbell flow uses just one PC as subscriber (mirrors the official
phone app's behavior when receiving an incoming ring).

Both flows: we munge Janus's `setup:actpass` SDP offer to `setup:active` so
aiortc, as RFC-compliant answerer, MUST become passive (DTLS server). This
prevents the both-active deadlock we hit before.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

import io

from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRecorder
from aiortc.mediastreams import MediaStreamTrack

from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    MONITOR_DEFAULT_DURATION_S,
    PASSIVE_HOLD_AFTER_END_S,
    RECORDINGS_SUBDIR,
    SDP_OFFER_GATHER_TIMEOUT_S,
    SIGNAL_CAMERA_REFRESH,
)

if TYPE_CHECKING:
    from .coordinator import AiphoneCoordinator

_LOGGER = logging.getLogger(__name__)


def now_sid() -> str:
    n = datetime.now()
    return n.strftime("%Y%m%d%H%M%S") + f"{n.microsecond:06d}"


def _strip_extra_fp(sdp: str) -> str:
    """Janus's DTLS parser only handles the first fingerprint reliably."""
    return "\r\n".join(
        ln for ln in sdp.split("\r\n")
        if not (ln.startswith("a=fingerprint:") and not ln.startswith("a=fingerprint:sha-256"))
    )


def _filename_safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s) or "recording"


def _log_audio_section(tag: str, sdp: str) -> None:
    """Print the m=audio media block + its codec/rtpmap/direction lines."""
    in_audio = False
    lines: list[str] = []
    for ln in sdp.splitlines():
        if ln.startswith("m="):
            in_audio = ln.startswith("m=audio")
            if in_audio:
                lines.append(ln)
            continue
        if in_audio and ln.startswith(("a=rtpmap:", "a=fmtp:", "a=sendrecv",
                                       "a=sendonly", "a=recvonly", "a=inactive",
                                       "a=mid:", "c=")):
            lines.append(ln)
    _LOGGER.info("%s audio block:\n  %s", tag, "\n  ".join(lines) if lines else "(none)")


class _PassthroughVideoTrack(MediaStreamTrack):
    """Tees frames to MediaRecorder while exposing the latest one as a snapshot."""

    kind = "video"

    def __init__(self, source: MediaStreamTrack, holder: VideoCapture) -> None:
        super().__init__()
        self._source = source
        self._holder = holder

    async def recv(self):
        frame = await self._source.recv()
        self._holder._latest_video_frame = frame
        return frame


def _frame_to_jpeg(frame) -> bytes | None:
    try:
        img = frame.to_image()
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()
    except Exception:
        _LOGGER.exception("frame→jpeg conversion failed")
        return None


async def _log_inbound_stats(pc: RTCPeerConnection, tag: str) -> None:
    """Dump per-track packetsReceived / bytesReceived from aiortc stats."""
    try:
        report = await pc.getStats()
    except Exception:
        _LOGGER.warning("%s getStats failed", tag, exc_info=True)
        return
    for stat in report.values():
        if getattr(stat, "type", "") == "inbound-rtp":
            _LOGGER.info(
                "%s inbound-rtp kind=%s codec=%s pkts=%s bytes=%s",
                tag,
                getattr(stat, "kind", "?"),
                getattr(stat, "codec", getattr(stat, "mimeType", "?")),
                getattr(stat, "packetsReceived", "?"),
                getattr(stat, "bytesReceived", "?"),
            )


class VideoCapture:
    """Owns active capture state. Single instance per coordinator."""

    def __init__(self, coord: AiphoneCoordinator) -> None:
        self.coord = coord
        self._lock = asyncio.Lock()
        self._latest_video_frame: Any = None  # av.VideoFrame; lazily JPEG-encoded

        # passive (doorbell ring)
        self._passive_pc: RTCPeerConnection | None = None
        self._passive_recorder: MediaRecorder | None = None
        self._passive_path: Path | None = None
        self._passive_cid: str | None = None
        self._passive_offer_fut: asyncio.Future | None = None

        # active (monitor)
        self._mon_pc1: RTCPeerConnection | None = None
        self._mon_pc2: RTCPeerConnection | None = None
        self._mon_recorder: MediaRecorder | None = None
        self._mon_path: Path | None = None
        self._mon_cid: str | None = None
        self._mon_fut_31001: asyncio.Future | None = None
        self._mon_fut_24021: asyncio.Future | None = None
        self._mon_fut_31011: asyncio.Future | None = None
        self._mon_fut_31012: asyncio.Future | None = None

    @property
    def recordings_dir(self) -> Path:
        d = Path(self.coord.hass.config.path(RECORDINGS_SUBDIR))
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def async_live_jpeg(self) -> bytes | None:
        """Return JPEG of the most recently received video frame, or None."""
        frame = self._latest_video_frame
        if frame is None:
            return None
        return await self.coord.hass.async_add_executor_job(_frame_to_jpeg, frame)

    @property
    def latest_recording(self) -> Path | None:
        try:
            files = sorted(self.recordings_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
            return files[-1] if files else None
        except OSError:
            return None

    # ------------------------------------------------------------------
    # signaling routing — coordinator forwards relevant MQTT messages
    # ------------------------------------------------------------------
    def on_signal(self, mid: str, raw: dict) -> None:
        head = raw.get("HEADER", {}) or {}
        body = raw.get("BODY", {}) or {}
        cid = head.get("CID")

        # passive doorbell flow
        if cid is not None and cid == self._passive_cid:
            if mid == "31011" and self._passive_offer_fut and not self._passive_offer_fut.done():
                self._passive_offer_fut.set_result(raw)

        # active monitor flow
        if cid is not None and cid == self._mon_cid:
            if mid == "31001" and self._mon_fut_31001 and not self._mon_fut_31001.done():
                self._mon_fut_31001.set_result(body.get("SDP", ""))
            elif mid == "24021" and self._mon_fut_24021 and not self._mon_fut_24021.done():
                self._mon_fut_24021.set_result(head.get("RSLT"))
            elif mid == "31011" and self._mon_fut_31011 and not self._mon_fut_31011.done():
                self._mon_fut_31011.set_result(body.get("SDP", ""))
            elif mid == "31012" and self._mon_fut_31012 and not self._mon_fut_31012.done():
                self._mon_fut_31012.set_result(head.get("RSLT"))

    # ------------------------------------------------------------------
    # PASSIVE — triggered by MID 23001 (doorbell ring)
    # ------------------------------------------------------------------
    async def passive_capture(self, cid: str, dsp1: str) -> None:
        if not await self._lock.acquire():
            return
        try:
            await self._passive_run(cid, dsp1)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("passive capture failed")
        finally:
            await self._passive_teardown()
            self._lock.release()

    async def _passive_run(self, cid: str, dsp1: str) -> None:
        if self._passive_pc is not None:
            _LOGGER.warning("passive already in progress, skipping")
            return
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._passive_path = self.recordings_dir / f"{ts}-{_filename_safe(dsp1 or 'ring')}.mp4"
        self._passive_cid = cid
        _LOGGER.info("🎥 passive capture cid=%s dsp1=%s -> %s", cid[-30:], dsp1, self._passive_path)

        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        pc.addTransceiver("audio", direction="sendrecv")
        pc.addTransceiver("video", direction="recvonly")
        rec = MediaRecorder(str(self._passive_path))
        @pc.on("track")
        def _on_track(track):
            _LOGGER.info("🎥 passive track: %s", track.kind)
            if track.kind == "video":
                rec.addTrack(_PassthroughVideoTrack(track, self))
            else:
                rec.addTrack(track)
        self._passive_pc = pc
        self._passive_recorder = rec

        # Step 1: 30011 with empty body (subscribe to wp2med stream in our room)
        pcliid = self.coord.sndtpc.rsplit("/", 1)[-1]
        self._passive_offer_fut = asyncio.get_event_loop().create_future()
        msg = {"HEADER": {
            "MID": "30011", "VER": "1.0", "SYS": "2",
            "CLIID": self.coord.cliid, "PCLIID": pcliid,
            "RCVTPC": self.coord.rcvtpc, "RLS": "0",
            "RSLT": 0, "LEN": 0, "SID": now_sid(), "CID": cid,
        }, "BODY": {}}
        self.coord.publish(msg)

        # Step 2: wait 31011 with Janus offer SDP
        try:
            offer_msg = await asyncio.wait_for(self._passive_offer_fut, timeout=8)
        except asyncio.TimeoutError:
            _LOGGER.error("31011 timeout (passive)")
            return
        offer_sdp = offer_msg.get("BODY", {}).get("SDP", "")
        if not offer_sdp:
            _LOGGER.error("31011 missing SDP body")
            return
        _log_audio_section("passive janus offer", offer_sdp)

        # Step 3: setRemoteDescription with actpass→active munge, createAnswer
        offer_munged = offer_sdp.replace("a=setup:actpass", "a=setup:active")
        try:
            await pc.setRemoteDescription(RTCSessionDescription(offer_munged, "offer"))
            ans = await pc.createAnswer()
            await pc.setLocalDescription(ans)
        except Exception:
            _LOGGER.exception("passive answer setup failed")
            return
        end = time.time() + SDP_OFFER_GATHER_TIMEOUT_S
        while pc.iceGatheringState != "complete" and time.time() < end:
            await asyncio.sleep(0.1)
        answer_sdp = _strip_extra_fp(pc.localDescription.sdp)

        # Step 4: 30012 with our answer
        msg2 = {"HEADER": {
            "MID": "30012", "VER": "1.0", "SYS": "2",
            "CLIID": self.coord.cliid, "PCLIID": pcliid,
            "RCVTPC": self.coord.rcvtpc, "RLS": "0",
            "RSLT": 0, "LEN": len(answer_sdp), "SID": now_sid(), "CID": cid,
        }, "BODY": {"SDP": answer_sdp}}
        self.coord.publish(msg2)

        await rec.start()
        _LOGGER.info("🎬 passive recorder started — will stop %ss after 24002",
                     PASSIVE_HOLD_AFTER_END_S)

        # Hold; coordinator's 24002 handler will call stop()
        try:
            # Cap at RING_TIMEOUT_S * 2 in case 24002 never arrives
            await asyncio.sleep(120)
        except asyncio.CancelledError:
            pass

    async def passive_finalize(self, delay_s: int = PASSIVE_HOLD_AFTER_END_S) -> None:
        """Called from coordinator on 24002 — wait briefly then stop."""
        if self._passive_pc is None:
            return
        await asyncio.sleep(delay_s)
        await self._passive_teardown()

    async def _passive_teardown(self) -> None:
        rec, pc, path = self._passive_recorder, self._passive_pc, self._passive_path
        self._passive_pc = self._passive_recorder = None
        self._passive_path = self._passive_cid = None
        self._passive_offer_fut = None
        if rec is not None:
            try:
                await rec.stop()
            except Exception:
                _LOGGER.warning("passive recorder.stop failed", exc_info=True)
        if pc is not None:
            await _log_inbound_stats(pc, "passive")
            try:
                await pc.close()
            except Exception:
                pass
        if path is not None and path.exists() and path.stat().st_size > 1000:
            _LOGGER.info("💾 passive recorded %s (%d B)", path, path.stat().st_size)
            async_dispatcher_send(self.coord.hass, SIGNAL_CAMERA_REFRESH)

    # ------------------------------------------------------------------
    # ACTIVE — monitor button press
    # ------------------------------------------------------------------
    async def monitor_capture(self, duration_s: int = MONITOR_DEFAULT_DURATION_S) -> None:
        if self._lock.locked():
            _LOGGER.warning("monitor: another capture in progress, skipping")
            return
        async with self._lock:
            try:
                await self._monitor_run(duration_s)
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("monitor capture failed")
            finally:
                await self._monitor_teardown()

    async def _monitor_run(self, duration_s: int) -> None:
        # PC #1 — publisher placeholder
        pc1 = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        pc1.addTransceiver("audio", direction="sendrecv")
        offer1 = await pc1.createOffer()
        await pc1.setLocalDescription(RTCSessionDescription(_strip_extra_fp(offer1.sdp), "offer"))
        end = time.time() + SDP_OFFER_GATHER_TIMEOUT_S
        while pc1.iceGatheringState != "complete" and time.time() < end:
            await asyncio.sleep(0.1)
        sdp_offer1 = pc1.localDescription.sdp
        cid = self.coord.cliid + now_sid()
        self._mon_cid = cid
        self._mon_pc1 = pc1
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._mon_path = self.recordings_dir / f"monitor-{ts}.mp4"
        _LOGGER.info("🎥 monitor cid=%s -> %s", cid[-30:], self._mon_path)

        # PC #2 — subscriber
        pc2 = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        pc2.addTransceiver("audio", direction="recvonly")
        pc2.addTransceiver("video", direction="recvonly")
        rec = MediaRecorder(str(self._mon_path))
        @pc2.on("track")
        def _on_track(track):
            _LOGGER.info("🎥 monitor track: %s", track.kind)
            if track.kind == "video":
                rec.addTrack(_PassthroughVideoTrack(track, self))
            else:
                rec.addTrack(track)
        self._mon_pc2 = pc2
        self._mon_recorder = rec

        loop = asyncio.get_event_loop()
        self._mon_fut_31001 = loop.create_future()
        self._mon_fut_24021 = loop.create_future()
        self._mon_fut_31011 = loop.create_future()
        self._mon_fut_31012 = loop.create_future()

        pcliid = self.coord.sndtpc.rsplit("/", 1)[-1]

        # Step 1: 30001 publisher
        self.coord.publish({"HEADER": {
            "MID": "30001", "VER": "1.0", "SYS": "2",
            "CLIID": self.coord.cliid, "RCVTPC": self.coord.rcvtpc, "RLS": "0",
            "RSLT": 0, "LEN": len(sdp_offer1), "SID": now_sid(), "CID": cid,
        }, "BODY": {"SDP": sdp_offer1}})
        sdp_a1 = await asyncio.wait_for(self._mon_fut_31001, timeout=8)
        await pc1.setRemoteDescription(RTCSessionDescription(sdp_a1, "answer"))

        # Step 2: 23021 MNT_REQ
        self.coord.publish({"HEADER": {
            "MID": "23021", "VER": "1.0", "SYS": "2",
            "CLIID": self.coord.cliid, "PCLIID": pcliid,
            "DSP1": self.coord.termname, "DSP2": "@",
            "CKIND": 1, "CID": cid,
            "RECKIND": 0, "AVID": 0,
            "SNDTPC": self.coord.sndtpc, "RCVTPC": self.coord.rcvtpc,
            "REASON": 0, "TMKIND": 5, "TMID": 1281,
            "RSLT": 0, "LEN": 0, "SID": now_sid(),
        }})
        rslt = await asyncio.wait_for(self._mon_fut_24021, timeout=8)
        if rslt != 200:
            _LOGGER.error("24021 RSLT=%s — monitor rejected", rslt)
            return

        # Step 3: 30011 subscriber claim
        self.coord.publish({"HEADER": {
            "MID": "30011", "VER": "1.0", "SYS": "2",
            "CLIID": self.coord.cliid, "PCLIID": pcliid,
            "RCVTPC": self.coord.rcvtpc, "RLS": "0",
            "RSLT": 0, "LEN": 0, "SID": now_sid(), "CID": cid,
        }, "BODY": {}})
        sdp_o2 = await asyncio.wait_for(self._mon_fut_31011, timeout=8)
        _log_audio_section("monitor janus offer", sdp_o2)
        sdp_o2_munged = sdp_o2.replace("a=setup:actpass", "a=setup:active")
        await pc2.setRemoteDescription(RTCSessionDescription(sdp_o2_munged, "offer"))

        # Step 4: 30012 answer
        ans2 = await pc2.createAnswer()
        await pc2.setLocalDescription(RTCSessionDescription(_strip_extra_fp(ans2.sdp), "answer"))
        end = time.time() + SDP_OFFER_GATHER_TIMEOUT_S
        while pc2.iceGatheringState != "complete" and time.time() < end:
            await asyncio.sleep(0.1)
        answer2 = pc2.localDescription.sdp
        self.coord.publish({"HEADER": {
            "MID": "30012", "VER": "1.0", "SYS": "2",
            "CLIID": self.coord.cliid, "PCLIID": pcliid,
            "RCVTPC": self.coord.rcvtpc, "RLS": "0",
            "RSLT": 0, "LEN": len(answer2), "SID": now_sid(), "CID": cid,
        }, "BODY": {"SDP": answer2}})
        try:
            await asyncio.wait_for(self._mon_fut_31012, timeout=6)
        except asyncio.TimeoutError:
            _LOGGER.warning("31012 timeout (non-fatal)")

        await rec.start()
        _LOGGER.info("🎬 monitor recording, holding %ss", duration_s)
        await asyncio.sleep(duration_s)

    async def aclose(self) -> None:
        """Coordinator shutdown — drop any in-flight capture cleanly."""
        await self._passive_teardown()
        await self._monitor_teardown()

    async def _monitor_teardown(self) -> None:
        rec, pc1, pc2, path = self._mon_recorder, self._mon_pc1, self._mon_pc2, self._mon_path
        self._mon_pc1 = self._mon_pc2 = self._mon_recorder = None
        self._mon_path = self._mon_cid = None
        self._mon_fut_31001 = self._mon_fut_24021 = None
        self._mon_fut_31011 = self._mon_fut_31012 = None
        if rec is not None:
            try:
                await rec.stop()
            except Exception:
                _LOGGER.warning("monitor recorder.stop failed", exc_info=True)
        if pc2 is not None:
            await _log_inbound_stats(pc2, "monitor")
        for pc in (pc2, pc1):
            if pc is not None:
                try:
                    await pc.close()
                except Exception:
                    pass
        if path is not None and path.exists() and path.stat().st_size > 1000:
            _LOGGER.info("💾 monitor recorded %s (%d B)", path, path.stat().st_size)
            async_dispatcher_send(self.coord.hass, SIGNAL_CAMERA_REFRESH)
