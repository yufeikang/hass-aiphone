# Aiphone WP-2MED — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

English | [日本語](README.ja.md)

> ⚠️ **Unofficial, independent project — not affiliated with Aiphone Co., Ltd.** Use at your own risk. By installing or using this software you accept the [DISCLAIMER](DISCLAIMER.md) in full.

Native Home Assistant integration for **Aiphone WP-2MED** video intercoms (single-family / 戸建 model, sold in Japan as part of the [VIXUS / VKZ-R](https://www.aiphone.co.jp/products/business/vkz/) series).

This integration talks directly to the unit's AWS IoT cloud over mTLS — the same channel the official iOS/Android app uses — and exposes doorbell events, live snapshots, on-demand monitor, recording, answer, and electric strike unlock as native HA entities. **No cloud relay, no scraping, no polling**: the integration receives push events from AWS IoT MQTT in real time.

> **Status**: Phase 2 features are working in production for one user (the author). Phase 3 (answer / unlock) is implemented but partially untested. See [§ Status](#status) below.

---

## Features

### Sensors

| Entity | Type | Description |
|---|---|---|
| `binary_sensor.<unit>_doorbell` | Occupancy | Flips `on` while the door station is ringing |
| `sensor.<unit>_doorbell_state` | string | `idle` / `ringing` / `answered` |
| `sensor.<unit>_last_caller` | string | DSP1 from the last ring (typically "玄関1") |

### Camera

| Entity | Description |
|---|---|
| `camera.<unit>_entrance` | JPEG snapshot — uses the **live frame** from any in-progress capture; falls back to the most recent finalized mp4 |

### Buttons

| Entity | Action |
|---|---|
| `button.<unit>_monitor` | On-demand 30-second active monitor (camera-on, no ring, doesn't bother other paired clients) |
| `button.<unit>_answer` | Send `MID 24000 RSLT=200` — accept the currently-ringing call. Opens audio, stops the unit ringing, suppresses other clients' notifications. |

### Lock

| Entity | Action |
|---|---|
| `lock.<unit>_door` | Send `MID 26021 SET_UNLOCK_REQ` to the unit's relay output (electric strike). Momentary — HA reverts to "locked" after 5 s, mirroring the unit's ~3 s auto-relock. |

### Auto-recording

Every doorbell ring auto-records to `/config/aiphone/recordings/<ts>-<caller>.mp4`. Active monitor sessions save as `monitor-<ts>.mp4`. Recording continues for 8 s after the call ends to flush mp4 mux.

---

## How it works

```
WP-2MED ──── AWS IoT Core (Tokyo) ───┐
   │  MQTT mTLS port 8883            │
   │  ALPN x-amzn-mqtt-ca            │
                                     ▼
                            HA (this integration)
                                     │
                                     ├─► binary_sensor / sensor
                                     ├─► button (monitor / answer)
                                     ├─► lock
                                     └─► camera + auto-recorder (aiortc)
```

- **Pairing**: same protocol the iOS app uses — LAN UDP discovery (port 51711/51712), TLS-52712 OTP exchange, HTTPS `/registClient` to get a client cert (RSA-2048, valid until 2070), then `01005` to register a display name. The whole sequence happens inside the **Home Assistant config flow** — no external tools.
- **Doorbell events**: subscribe to `<unit-mac>/#`, parse `MID 23001` / `24000` / `24002` to drive the doorbell state machine.
- **Video**: when a ring fires (or the monitor button is pressed), the integration speaks Aiphone's full SDP-over-MQTT WebRTC dance against the AWS Tokyo Janus VideoRoom SFU. We use `aiortc` as the local DTLS-SRTP peer; recordings land as MP4. A passthrough video track also exposes the live frame as a JPEG without waiting for the file to finalize.

---

## Requirements

- Home Assistant 2024.3 or newer (Python 3.11+)
- An Aiphone **WP-2MED** unit on the same LAN as Home Assistant during initial pairing (subsequent operation is internet-only)
- Outbound HTTPS to `api.aiphone-app.net` (only during pairing)
- Outbound MQTT to `*.iot.ap-northeast-1.amazonaws.com:8883` (steady state)
- Free pairing slot on the unit (戸建 limit: 4 paired devices including all family phones)

The integration auto-installs `aiortc>=1.14.0` and `av>=10.0.0` on first load. On a Raspberry Pi, expect the first install to take a few minutes.

---

## Installation

### HACS (recommended once published)

1. Add this repository as a custom repository in HACS (category: integration)
2. Search for "Aiphone WP-2MED" and install
3. Restart Home Assistant

### Manual

```bash
# In your HA config directory
cd config/custom_components
git clone https://github.com/yufeikang/hass-aiphone.git aiphone-tmp
mv aiphone-tmp/custom_components/aiphone .
rm -rf aiphone-tmp
```

Restart Home Assistant.

---

## Pairing

1. **On the WP-2MED unit**: 設定 → 各種設定 → アプリ連携 → 端末追加 (or similar "add device" menu).
2. **In Home Assistant**: Settings → Devices & Services → Add Integration → search "Aiphone".
3. Enter a display name (this is what shows on the unit's call list — e.g. "HA").
4. Click Submit. Pairing finishes in 5–10 seconds. The new device appears on the unit's screen as one of the paired clients.

If pairing fails, make sure:
- HA is on the same LAN as the unit (UDP broadcast must reach 255.255.255.255:51711)
- The unit is currently in "端末追加" mode (it leaves this mode after ~30 s)
- No firewall is blocking outbound 443 to `api.aiphone-app.net`

---

## Status

| Feature | Status |
|---|---|
| Pairing in HA UI | ✅ Working |
| Doorbell ring events | ✅ Working in production |
| Auto-record on ring | ✅ Working in production |
| `camera.entrance` snapshots | ✅ Working — live frame + mp4 fallback |
| `button.monitor` (on-demand camera) | ✅ Working — 30 s mp4 captured end-to-end |
| `button.answer` (24000 RSLT=200) | ⚠️ **Implemented, untested with real ring** |
| `lock.door` (26021 unlock) | ⚠️ Implemented, **physical effect not verifiable** by author (no electric strike wired) |
| Audio in recordings | ❌ Not yet — cloud only opens RTP audio after a real-ring `24000`. Pending answer-button test. |
| Hangup | ❌ Not implemented (likely `24002 RSLT=603` + `30031` release) |
| Two-way audio (TTS / AI assistant talking back) | ❌ Not implemented — PC1 leaves an audio-sendrecv transceiver open as a placeholder for this. |
| HACS distribution | ❌ Not yet (this README + `hacs.json` are the prep) |

---

## Known issues

- **First snapshot lag**: ~3 seconds between doorbell ring and first JPEG frame, dominated by SDP exchange + DTLS handshake. The `camera` entity falls back to the previous mp4's last frame during this window.
- **Hangup workaround**: the integration has no hangup button yet. After `button.answer`, the call ends naturally when the unit times out (or the visitor walks away). The recording stops 8 s after the unit broadcasts `MID 24002`.
- **Multi-client subscriber slot**: the cloud admits only one subscriber per ring. If the official phone app subscribes first, HA's recording for that ring may show `RSLT=400` and produce no video. In practice this hasn't been an issue because we typically subscribe within ~100 ms of the ring.

---

## Development

```bash
git clone https://github.com/yufeikang/hass-aiphone.git
cd hass-aiphone
uv venv
uv pip install -e ".[dev]"
```

Run tests (when there are any):

```bash
pytest
```

The integration is two layers:

```
custom_components/aiphone/
├── __init__.py            # config-entry setup + v1→v2 migration
├── manifest.json
├── const.py
├── config_flow.py         # multi-step pairing UI
├── pairing.py             # blocking LAN UDP + TLS + /registClient flow
├── coordinator.py         # MQTT (paho-mqtt) + state machine
├── media.py               # aiortc; passive + monitor capture; live frame tee
├── binary_sensor.py
├── sensor.py
├── button.py              # Monitor + Answer
├── camera.py              # Live frame → JPEG; mp4 fallback
└── lock.py                # 26021 unlock
```

Protocol-level questions (wire format, MID table, edge cases) are best raised on the issue tracker.

---

## Acknowledgements

This project was built from scratch via static analysis of the publicly distributed Android application and observation of the author's own network traffic on the author's own equipment. No proprietary documentation, internal source code, or non-public cryptographic material was used. There is no public Aiphone SDK.

---

## Disclaimer

This is an **independent, unofficial** community project. It is **not affiliated with, endorsed by, or sponsored by Aiphone Co., Ltd.** "Aiphone", "WP-2MED", "VKZ-R", and "VIXUS" are trademarks of Aiphone Co., Ltd.

Use of this integration **may violate** the manufacturer's Terms of Service. The user assumes all risk. Read the full [DISCLAIMER](DISCLAIMER.md) before installing.

For takedown requests from rights-holders, please open an issue or contact the maintainer.

---

## License

MIT — see [LICENSE](LICENSE). Use of the code is subject to the additional non-warranty and use-at-your-own-risk terms set out in [DISCLAIMER](DISCLAIMER.md).
