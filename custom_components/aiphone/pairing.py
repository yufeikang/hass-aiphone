"""Aiphone pairing helper.

Independent reimplementation derived from observation of public network traffic. Runs the
discovery → TLS exchange → cloud cert provisioning → termname registration
sequence and returns the resulting credentials as a dict.

Whole flow blocks the calling thread; intended to be invoked via
`hass.async_add_executor_job(pair_aiphone, termname)`.
"""
from __future__ import annotations

import json
import logging
import socket
import ssl
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from typing import Any

from .const import (
    API_BASE,
    DEFAULT_IOT_HOST,
    PAIRING_DISCOVERY_TIMEOUT,
    PAIRING_TLS_TIMEOUT,
    UDP_BCAST_PORT,
    UDP_RECV_PORT,
)

_LOGGER = logging.getLogger(__name__)


class PairingError(Exception):
    """Base class for pairing errors."""


class WPNotInPairingMode(PairingError):
    """WP-2MED did not respond to UDP discovery — likely not in pairing mode."""


class TLSConnectFailed(PairingError):
    """Could not open TLS to WP-2MED on its TLS port."""


class OTPVerifyFailed(PairingError):
    """01003 OTP verify returned non-zero RSLT."""


class CloudRegistrationFailed(PairingError):
    """/registClient returned a non-200 or invalid response."""


class TermNameRegistrationFailed(PairingError):
    """01005 termname registration failed (RSLT != 0)."""


# ---------------------------------------------------------------------------
# wire helpers
# ---------------------------------------------------------------------------
def _now_sid() -> str:
    n = datetime.now()
    return n.strftime("%Y%m%d%H%M%S") + f"{n.microsecond:06d}"


def _make_pkt(mid: str, body: dict | None = None) -> bytes:
    msg: dict[str, Any] = {"HEADER": {"MID": mid, "VER": "1.0"}}
    if body:
        msg["BODY"] = body
    return (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")


def _parse(data: bytes) -> dict:
    raw = json.loads(data.decode("utf-8", "replace").rstrip("\n"))
    flat: dict[str, Any] = {}
    flat.update(raw.get("HEADER", {}))
    flat.update(raw.get("BODY", {}))
    return flat


# ---------------------------------------------------------------------------
# UDP discovery
# ---------------------------------------------------------------------------
def _discover() -> tuple[str, int]:
    """Send 01001 broadcasts; listen for 11001. Return (ip, tls_port)."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("0.0.0.0", UDP_RECV_PORT))

    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    pkt = _make_pkt("01001")
    deadline = time.monotonic() + PAIRING_DISCOVERY_TIMEOUT
    last_send = 0.0
    listener.settimeout(0.5)
    try:
        while time.monotonic() < deadline:
            if time.monotonic() - last_send > 0.5:
                sender.sendto(pkt, ("255.255.255.255", UDP_BCAST_PORT))
                last_send = time.monotonic()
            try:
                data, addr = listener.recvfrom(2048)
            except socket.timeout:
                continue
            try:
                msg = _parse(data)
            except (json.JSONDecodeError, ValueError):
                continue
            if msg.get("MID") == "11001" and str(msg.get("RSLT", "0")) in ("0", "0.0"):
                return addr[0], int(msg["PORT"])
    finally:
        listener.close()
        sender.close()
    raise WPNotInPairingMode(
        "WP-2MED did not respond. Make sure the unit is in 端末追加 (add-device) mode."
    )


# ---------------------------------------------------------------------------
# TLS to WP-2MED
# ---------------------------------------------------------------------------
def _make_tls_ctx() -> ssl.SSLContext:
    """WP-2MED's wolfSSL stack lacks RFC 5746 secure renegotiation; allow legacy."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
    try:
        ctx.set_ciphers("ALL:@SECLEVEL=0")
    except ssl.SSLError:
        ctx.set_ciphers("DEFAULT@SECLEVEL=0")
    return ctx


def _tls_send_recv(s: ssl.SSLSocket, payload: bytes, expect_mid: str) -> dict:
    s.sendall(payload)
    s.settimeout(10)
    buf = b""
    while b"\n" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
        try:
            json.loads(buf.decode("utf-8"))
            break
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    msg = _parse(buf.split(b"\n", 1)[0])
    if msg.get("MID") != expect_mid:
        _LOGGER.warning("TLS unexpected MID; wanted %s, got %s", expect_mid, msg)
    return msg


# ---------------------------------------------------------------------------
# cloud /registClient (synchronous urllib so this stays a single executor job)
# ---------------------------------------------------------------------------
def _regist_client(otp: str, cliid: str) -> dict:
    body = {
        "BODY": {
            "OTPASS":    otp,
            "OSKIND":    1,
            "CLIID":     cliid,
            "SYSVER":    "3.08",
            "RCVTPC":    "",
            "SNDTPC":    "",
            "SRVROOTCA": "",
            "SRVURL":    "",
            "SEQID":     1,
            "SYS":       "2",
        }
    }
    req = urllib.request.Request(
        f"{API_BASE}/registClient",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "AIPHONE IP/3.08"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise CloudRegistrationFailed(f"/registClient HTTP {e.code}") from e
    try:
        return json.loads(text)["BODY"]
    except (json.JSONDecodeError, KeyError) as e:
        raise CloudRegistrationFailed(f"/registClient invalid JSON: {text[:200]}") from e


# ---------------------------------------------------------------------------
# main entry point — single executor job
# ---------------------------------------------------------------------------
def pair_aiphone(termname: str) -> dict:
    """Run the full pairing flow synchronously. Returns credential dict."""
    cliid_local = str(uuid.uuid4()).upper()
    _LOGGER.info("aiphone pairing — local CLIID %s, termname %s", cliid_local, termname)

    # --- UDP discover ---
    ip, port = _discover()
    _LOGGER.info("WP-2MED discovered at %s:%s", ip, port)

    # --- single TLS session: 01002 → 01003 → /registClient → 01005 ---
    ctx = _make_tls_ctx()
    raw = socket.create_connection((ip, port), timeout=PAIRING_TLS_TIMEOUT)
    try:
        s = ctx.wrap_socket(raw, server_hostname=ip)
    except ssl.SSLError as e:
        raise TLSConnectFailed(str(e)) from e

    try:
        # 01002 — request OTP
        msg = _tls_send_recv(
            s,
            _make_pkt("01002", {"CLIID": cliid_local}),
            "11002",
        )
        if str(msg.get("RSLT", "0")) not in ("0", "0.0"):
            raise OTPVerifyFailed(f"01002 refused: {msg}")
        otp = msg["OTPASS"]
        screen_code = otp[-4:]
        _LOGGER.info("OTP received; last 4 = %s", screen_code)

        # 01003 — verify with last 4 chars (NOT the full UUID)
        v = _tls_send_recv(s, _make_pkt("01003", {"OTPASS": screen_code}), "11003")
        if str(v.get("RSLT", "1")) not in ("0", "0.0"):
            raise OTPVerifyFailed(f"01003 verify failed: {v}")

        # /registClient — cloud cert provisioning
        cloud = _regist_client(otp, cliid_local)
        cert = cloud.get("CERT")
        seckey = cloud.get("SECKEY") or cloud.get("DVCKEY")
        new_cliid = cloud.get("CLIID")
        rcvtpc = cloud.get("RCVTPC")
        sndtpc = cloud.get("SNDTPC")
        iot_host = cloud.get("URL", DEFAULT_IOT_HOST)
        if not (cert and seckey and new_cliid and rcvtpc and sndtpc):
            raise CloudRegistrationFailed(
                f"missing fields in /registClient response: {list(cloud.keys())}"
            )

        # 01005 — register termname using server-assigned CLIID + RCVTPC
        r5 = _tls_send_recv(
            s,
            _make_pkt("01005", {"CLIID": new_cliid, "TERMNM": termname, "TERMTPC": rcvtpc}),
            "11005",
        )
        if str(r5.get("RSLT", "1")) not in ("0", "0.0"):
            raise TermNameRegistrationFailed(f"01005 failed: {r5}")

        unit_mac = rcvtpc.split("/", 1)[0]
        return {
            "cliid":      new_cliid,
            "iot_host":   iot_host,
            "sndtpc":     sndtpc,
            "rcvtpc":     rcvtpc,
            "cert_pem":   cert,
            "seckey_pem": seckey,
            "termname":   termname,
            "unit_mac":   unit_mac,
        }
    finally:
        try:
            s.close()
        except Exception:
            pass
