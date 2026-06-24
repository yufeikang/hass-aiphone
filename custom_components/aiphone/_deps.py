"""Runtime dependency shim for aiortc.

aiortc (latest release 1.14.0) caps its PyAV dependency at ``av<17``, but Home
Assistant's core stack (the ``stream`` / ``generic`` / ``uiprotect`` components)
pins ``av==17.0.1`` and enforces that as a hard constraint when installing *any*
integration requirement.  So listing ``aiortc>=1.14.0`` in ``manifest.json``
makes HA's uv resolver fail at startup with::

    Because aiortc==1.14.0 depends on av>=14.0.0,<17.0.0 and av==17.0.1,
    we can conclude that aiortc==1.14.0 cannot be used.
    ... your requirements are unsatisfiable.

aiortc 1.14.0 actually runs fine on av 17 at runtime (verified: H264 decoder,
Opus encoder/decoder, ``av.AudioResampler`` and a full ``RTCPeerConnection``
lifecycle all work) — only its packaging metadata is over-restrictive.

HA's manifest ``requirements`` can't express ``--no-deps``, so we install aiortc
ourselves with ``--no-deps``.  That leaves HA's ``av==17.0.1`` untouched while
still getting aiortc onto ``sys.path``.  aiortc's *other* (non-conflicting)
dependencies stay in ``manifest.json`` and are installed by HA normally.

Remove this shim — and put ``aiortc>=...`` back in ``manifest.json`` — once
aiortc ships a release that allows ``av>=17``.
"""
from __future__ import annotations

import importlib
import logging
import os
import subprocess
import sys

from homeassistant.util.package import is_installed

_LOGGER = logging.getLogger(__name__)

# Matched for both the "already there?" check and the install. With --no-deps
# the av pin in aiortc's metadata is never read, so any 1.14.0+ release is fine.
AIORTC_REQUIREMENT = "aiortc>=1.14.0"


def ensure_runtime_deps() -> None:
    """Install aiortc with ``--no-deps`` if it isn't importable yet.

    Called at import time of :mod:`.media` (which runs in HA's executor thread,
    so a blocking subprocess is acceptable).  Idempotent: a no-op on every boot
    after aiortc is present, until the container image is rebuilt.
    """
    if is_installed(AIORTC_REQUIREMENT):
        return

    _LOGGER.warning(
        "aiortc not installed; installing %s with --no-deps so Home "
        "Assistant's av==17.0.1 is kept (aiortc's av<17 pin is overly strict "
        "but runtime-compatible). See custom_components/aiphone/_deps.py.",
        AIORTC_REQUIREMENT,
    )

    # Mirror homeassistant.util.package.install_package, minus the dependency
    # resolution. UV_SYSTEM_PYTHON=true is set in HA's environment, so uv
    # installs into the system site-packages (already on sys.path); no --target.
    args = [
        sys.executable, "-m", "uv", "pip", "install", "--quiet", "--no-deps",
        "--index-strategy", "unsafe-first-match", AIORTC_REQUIREMENT,
    ]
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        args, env=os.environ.copy(), capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise ImportError(
            f"aiphone: failed to install {AIORTC_REQUIREMENT!r}: "
            f"{(proc.stderr or proc.stdout).strip()}"
        )

    importlib.invalidate_caches()
    _LOGGER.info("aiortc installed successfully (--no-deps)")
