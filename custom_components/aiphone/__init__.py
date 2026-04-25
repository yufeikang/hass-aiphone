"""The Aiphone integration."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CERT_PEM,
    CONF_CLIID,
    CONF_IOT_HOST,
    CONF_RCVTPC,
    CONF_REGIST_RESPONSE,
    CONF_SECKEY_PEM,
    CONF_SNDTPC,
    CONF_TERMNAME,
    CONF_UNIT_MAC,
    CONFIG_VERSION,
    DEFAULT_IOT_HOST,
    DOMAIN,
)
from .coordinator import AiphoneCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.LOCK,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Aiphone from a config entry."""
    coordinator = AiphoneCoordinator(hass, entry)
    try:
        await coordinator.async_start()
    except Exception as err:
        _LOGGER.exception("Failed to start Aiphone coordinator: %s", err)
        return False

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: AiphoneCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_stop()
        return True
    return False


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate v1 (file-path) entries to v2 (inline credentials).

    v1: data = {"regist_response_path": "/config/aiphone/regist_response.json"}
    v2: data = {"cliid": "...", "cert_pem": "...", ...}
    """
    if entry.version >= CONFIG_VERSION:
        return True
    _LOGGER.info("Migrating Aiphone entry %s from v%s to v%s",
                 entry.entry_id, entry.version, CONFIG_VERSION)

    if entry.version == 1:
        path = entry.data.get(CONF_REGIST_RESPONSE)
        if not path:
            _LOGGER.error("v1 entry has no %s key", CONF_REGIST_RESPONSE)
            return False

        def _load() -> dict:
            return json.loads(Path(path).read_text())["body"]["BODY"]

        try:
            body = await hass.async_add_executor_job(_load)
        except Exception as err:
            _LOGGER.error("v1→v2 migration: cannot read %s: %s", path, err)
            return False

        rcvtpc = body["RCVTPC"]
        new_data = {
            CONF_CLIID:      body["CLIID"],
            CONF_IOT_HOST:   body.get("URL", DEFAULT_IOT_HOST),
            CONF_SNDTPC:     body["SNDTPC"],
            CONF_RCVTPC:     rcvtpc,
            CONF_CERT_PEM:   body["CERT"],
            CONF_SECKEY_PEM: body.get("SECKEY") or body.get("DVCKEY"),
            CONF_TERMNAME:   "PiBridge",
            CONF_UNIT_MAC:   rcvtpc.split("/", 1)[0],
        }
        hass.config_entries.async_update_entry(entry, data=new_data, version=CONFIG_VERSION)
        _LOGGER.info("v1→v2 migration succeeded for entry %s", entry.entry_id)
        return True

    return False
