"""Jump-host connection helper for Alive_Checks.

No connection is created at import time. Configure the jump host with environment
variables or pass values directly to ``create_jump_host_connection``.
"""

from __future__ import annotations

import os
from typing import Any

from netmiko import ConnectHandler


def create_jump_host_connection(
    *,
    device_type: str | None = None,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int | str | None = None,
    **extra: Any,
):
    """Create and return a Netmiko connection to a jump host.

    Environment fallback:
      JUMP_HOST_DEVICE_TYPE, JUMP_HOST_IP, JUMP_HOST_USERNAME,
      JUMP_HOST_PASSWORD, JUMP_HOST_PORT.
    """

    device = {
        "device_type": device_type or os.getenv("JUMP_HOST_DEVICE_TYPE", "linux"),
        "host": host or os.getenv("JUMP_HOST_IP"),
        "username": username or os.getenv("JUMP_HOST_USERNAME"),
        "password": password or os.getenv("JUMP_HOST_PASSWORD"),
        "port": int(port or os.getenv("JUMP_HOST_PORT", "22")),
    }
    device.update(extra)

    missing = [key for key, value in device.items() if key in {"host", "username", "password"} and not value]
    if missing:
        raise ValueError(
            "Missing jump-host configuration: "
            + ", ".join(missing)
            + ". Set JUMP_HOST_IP, JUMP_HOST_USERNAME, and JUMP_HOST_PASSWORD, "
            "or pass them to create_jump_host_connection()."
        )

    return ConnectHandler(**device)
