"""Reachability checks for network devices.

The direct check uses the local system ping command. The jump-host check expects
a Netmiko connection object or environment-based jump-host settings documented
in Connection.py.
"""

from __future__ import annotations

import argparse
import logging
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

from Connection import create_jump_host_connection

LOG_DIR = Path(__file__).resolve().parent / "logs"
logger = logging.getLogger(__name__)


def configure_logging(verbose: bool = False) -> None:
    """Configure console and file logging for CLI usage."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "alive_checks.log"),
            logging.StreamHandler(),
        ],
    )


def platform_check() -> str:
    """Return the ping count flag for the current OS."""

    return "n" if platform.system().lower() == "windows" else "c"


def _extract_loss_percent(ping_output: str) -> int | None:
    """Extract packet loss percentage from Windows or Unix ping output."""

    patterns = [
        r"(\d+)%\s*packet loss",
        r"\((\d+)%\s*loss\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, ping_output, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def alive_check(device_ip: str, count: int = 4, timeout_seconds: int = 20) -> str:
    """Ping a device from the local machine and return a human-readable result."""

    command = ["ping", f"-{platform_check()}", str(count), device_ip]
    logger.info("Starting direct ping check for %s", device_ip)

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Ping timed out for %s", device_ip)
        return f"Ping Failed for {device_ip}"
    except OSError as exc:
        logger.error("Ping command failed for %s: %s", device_ip, exc)
        return f"Ping Failed for {device_ip}"

    output = f"{result.stdout}\n{result.stderr}"
    loss_percent = _extract_loss_percent(output)

    if result.returncode == 0 and (loss_percent is None or loss_percent == 0):
        logger.info("Direct ping passed for %s", device_ip)
        return f"Ping Passed for {device_ip}"

    logger.warning("Direct ping failed for %s; packet loss=%s", device_ip, loss_percent)
    return f"Ping Failed for {device_ip}"


def jh_device_check(device_ip: str, connection: Any | None = None) -> dict[bool, list[int]] | None:
    """Ping a device from a jump host.

    Pass an existing Netmiko connection to ``connection`` or configure the
    jump-host environment variables described in Connection.py.
    """

    own_connection = False
    net_connect = connection

    try:
        if net_connect is None:
            net_connect = create_jump_host_connection()
            own_connection = True

        logger.info("Starting jump-host ping check for %s", device_ip)
        ping_result = net_connect.send_command_timing(
            command_string=f"ping -c 5 {device_ip}",
            read_timeout=120.0,
            last_read=2.0,
        )
        loss_percent = _extract_loss_percent(ping_result)

        if loss_percent is None and "ping statistics" not in ping_result:
            long_ping = net_connect.read_channel_timing(max_loops=10, last_read=10, read_timeout=120)
            loss_percent = _extract_loss_percent(long_ping)

        if loss_percent is None:
            logger.warning("Could not parse jump-host ping result for %s", device_ip)
            return None

        ok = loss_percent == 0
        logger.info("Jump-host ping result for %s: %s%% packet loss", device_ip, loss_percent)
        return {ok: [loss_percent]}

    except Exception as exc:  # Netmiko raises several connection/read exceptions.
        logger.error("Jump-host ping failed for %s: %s", device_ip, exc, exc_info=True)
        return None
    finally:
        if own_connection and net_connect is not None:
            try:
                net_connect.disconnect()
            except Exception:
                logger.debug("Jump-host disconnect failed", exc_info=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ping a device directly or through a jump host.")
    parser.add_argument("device_ip", help="Device IP or hostname to check")
    parser.add_argument("--jump-host", action="store_true", help="Run ping from the configured jump host")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    configure_logging(verbose=args.verbose)
    if args.jump_host:
        print(jh_device_check(args.device_ip))
    else:
        print(alive_check(args.device_ip))


if __name__ == "__main__":
    main()
