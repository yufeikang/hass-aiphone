"""Constants for the Aiphone integration."""
from __future__ import annotations

DOMAIN = "aiphone"
CONFIG_VERSION = 2

# Config-entry data keys (v2 stores credentials inline)
CONF_CLIID = "cliid"
CONF_IOT_HOST = "iot_host"
CONF_SNDTPC = "sndtpc"
CONF_RCVTPC = "rcvtpc"
CONF_CERT_PEM = "cert_pem"
CONF_SECKEY_PEM = "seckey_pem"
CONF_TERMNAME = "termname"
CONF_UNIT_MAC = "unit_mac"

# v1 (legacy)
CONF_REGIST_RESPONSE = "regist_response_path"

# AWS IoT defaults
DEFAULT_IOT_HOST = "a51k9cd2jjxpf-ats.iot.ap-northeast-1.amazonaws.com"
DEFAULT_IOT_PORT = 8883
ALPN_PROTO = "x-amzn-mqtt-ca"

# Internal dispatcher signals
SIGNAL_STATE_UPDATE = f"{DOMAIN}_state_update"
SIGNAL_CAMERA_REFRESH = f"{DOMAIN}_camera_refresh"

# Doorbell state machine
STATE_IDLE = "idle"
STATE_RINGING = "ringing"
STATE_ANSWERED = "answered"

# How long after a 23001 (ring) before we auto-clear to idle (in case 24002 is missed)
RING_TIMEOUT_S = 45

# Local pairing protocol
UDP_BCAST_PORT = 51711
UDP_RECV_PORT = 51712
API_BASE = "https://api.aiphone-app.net"
PAIRING_TLS_TIMEOUT = 15
PAIRING_DISCOVERY_TIMEOUT = 15

# Media capture
RECORDINGS_SUBDIR = "aiphone/recordings"     # under /config/
PASSIVE_HOLD_AFTER_END_S = 8                 # extra time after 24002 to flush mp4
MONITOR_DEFAULT_DURATION_S = 30
SDP_OFFER_GATHER_TIMEOUT_S = 4
