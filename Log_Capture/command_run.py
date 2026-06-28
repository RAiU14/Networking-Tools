"""Run show commands on network devices and save command output.

Inputs are provided by local CSV/XLSX files. Do not commit real device inventory,
passwords, output captures, or failure reports to Git.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
from pathlib import Path
from typing import Iterable

import pandas as pd
from netmiko import ConnectHandler

REQUIRED_DEVICE_COLUMNS = ["Hostname", "IP Address", "Device Type", "SSH Username", "SSH Password"]
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
logger = logging.getLogger("NetworkAutomation")


def configure_logging(log_dir: Path, verbose: bool = False) -> None:
    """Configure logging for CLI/GUI runs."""

    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_dir / f"{dt.date.today()}_network_automation.log"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def read_tabular_file(path: Path) -> pd.DataFrame:
    """Read a CSV/XLSX/XLS/XLSM file into a DataFrame."""

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls", ".xlsm"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported file type: {path.suffix}. Use .csv, .xlsx, .xls, or .xlsm.")


def read_commands(commands_file: Path) -> list[str]:
    """Read commands from the first column of a CSV/XLSX file."""

    logger.info("Reading command list from %s", commands_file.name)
    commands_df = read_tabular_file(commands_file)
    if commands_df.empty:
        return []
    commands = [str(value).strip() for value in commands_df.iloc[:, 0].dropna().tolist()]
    commands = [command for command in commands if command]
    logger.info("Loaded %s command(s)", len(commands))
    return commands


def validate_devices(devices_df: pd.DataFrame) -> pd.DataFrame:
    """Validate and clean the device inventory DataFrame."""

    missing = [column for column in REQUIRED_DEVICE_COLUMNS if column not in devices_df.columns]
    if missing:
        raise ValueError("Devices file is missing required column(s): " + ", ".join(missing))

    cleaned = devices_df.copy()
    cleaned = cleaned.dropna(how="all")
    for column in REQUIRED_DEVICE_COLUMNS:
        cleaned[column] = cleaned[column].astype("string").str.strip()

    empty_rows = cleaned[REQUIRED_DEVICE_COLUMNS].isna().any(axis=1) | (cleaned[REQUIRED_DEVICE_COLUMNS] == "").any(axis=1)
    if empty_rows.any():
        bad_indexes = [str(index + 2) for index in cleaned.index[empty_rows].tolist()]
        raise ValueError("Devices file has blank required values on spreadsheet row(s): " + ", ".join(bad_indexes))

    return cleaned


def sanitize_filename(value: str) -> str:
    """Return a filesystem-safe filename component."""

    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe.strip("._") or "device"


def device_params_from_row(device_info: pd.Series) -> dict[str, object]:
    """Build Netmiko connection parameters from a device inventory row."""

    return {
        "device_type": str(device_info["Device Type"]).lower().replace(" ", "_"),
        "host": str(device_info["IP Address"]),
        "username": str(device_info["SSH Username"]),
        "password": str(device_info["SSH Password"]),
        "timeout": 30,
    }


def execute_commands_on_device(device_info: pd.Series, commands: Iterable[str], output_dir: Path) -> str:
    """Execute commands on a single device and save output to a text file."""

    hostname = str(device_info["Hostname"])
    ip_address = str(device_info["IP Address"])
    commands = list(commands)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Connecting to %s (%s)", hostname, ip_address)
    try:
        connection = ConnectHandler(**device_params_from_row(device_info))
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = output_dir / f"{sanitize_filename(hostname)}_{sanitize_filename(ip_address)}_{timestamp}.txt"

        with filename.open("w", encoding="utf-8") as file:
            for index, command in enumerate(commands, start=1):
                logger.info("%s: running command %s/%s", hostname, index, len(commands))
                file.write(f"\n### Command {index}: {command}\n")
                try:
                    output = connection.send_command(command, read_timeout=60)
                    file.write(output)
                    if not output.endswith("\n"):
                        file.write("\n")
                except Exception as command_error:
                    message = f"ERROR executing {command!r}: {command_error}"
                    logger.error("%s", message)
                    file.write(message + "\n")
                file.write("#" * 72 + "\n")

        connection.disconnect()
        logger.info("Completed %s", hostname)
        return f"SUCCESS: {filename}"

    except Exception as error:
        message = f"ERROR - {hostname} ({ip_address}): {error}"
        logger.error("%s", message)
        return message


def save_failed_devices(failed_devices: list[dict[str, str]], output_dir: Path) -> Path | None:
    """Save failed devices to the output folder."""

    if not failed_devices:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    failed_file = output_dir / f"failed_devices_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with failed_file.open("w", encoding="utf-8") as file:
        file.write("FAILED DEVICES REPORT\n")
        file.write("=" * 40 + "\n")
        file.write(f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        file.write(f"Total Failed: {len(failed_devices)}\n")
        file.write("=" * 40 + "\n\n")
        for failed_device in failed_devices:
            file.write(f"Hostname: {failed_device['hostname']}\n")
            file.write(f"IP Address: {failed_device['ip']}\n")
            file.write(f"Reason: {failed_device['reason']}\n")
            file.write("-" * 40 + "\n")

    logger.info("Failed devices saved to %s", failed_file)
    return failed_file


def run_inventory(devices_file: Path, commands_file: Path, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, object]:
    """Run the full collection workflow and return a summary."""

    capture_dir = output_dir / "device_captures"
    report_dir = output_dir / "reports"

    logger.info("Network automation run started")
    devices_df = validate_devices(read_tabular_file(devices_file))
    commands = read_commands(commands_file)
    if not commands:
        raise ValueError("No commands found in the command file")

    successful = 0
    failed_devices: list[dict[str, str]] = []

    for index, device_row in devices_df.iterrows():
        hostname = str(device_row["Hostname"])
        ip_address = str(device_row["IP Address"])
        logger.info("Processing device %s/%s: %s", index + 1, len(devices_df), hostname)
        result = execute_commands_on_device(device_row, commands, capture_dir)
        if result.startswith("SUCCESS"):
            successful += 1
        else:
            failed_devices.append({"hostname": hostname, "ip": ip_address, "reason": result})

    failed_file = save_failed_devices(failed_devices, report_dir)
    total = len(devices_df)
    failed = len(failed_devices)
    success_rate = (successful / total) * 100 if total else 0.0

    summary = {
        "total": total,
        "successful": successful,
        "failed": failed,
        "success_rate": round(success_rate, 2),
        "output_dir": str(output_dir),
        "failed_report": str(failed_file) if failed_file else None,
    }
    logger.info("Automation completed: %s", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run network show commands from a device inventory file.")
    parser.add_argument("--devices", required=True, type=Path, help="Path to devices CSV/XLSX")
    parser.add_argument("--commands", required=True, type=Path, help="Path to commands CSV/XLSX")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Where captures/reports/logs are written")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.output_dir / "logs", verbose=args.verbose)
    summary = run_inventory(args.devices, args.commands, args.output_dir)
    print(summary)


if __name__ == "__main__":
    main()
