from __future__ import annotations

import argparse
import csv
import datetime as dt
import getpass
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import pandas as pd
REQUIRED_DEVICE_COLUMNS = ["Hostname", "IP Address", "Device Type", "SSH Username"]
PASSWORD_COLUMN = "SSH Password"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
DEFAULT_PASSWORD_ENV = "NETTOOLS_SSH_PASSWORD"
logger = logging.getLogger("NetworkAutomation")


def configure_logging(log_dir: Path, verbose: bool = False) -> None:
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
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls", ".xlsm"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported file type: {path.suffix}. Use .csv, .xlsx, .xls, or .xlsm.")


def read_commands(commands_file: Path) -> list[str]:
    logger.info("Reading command list from %s", commands_file.name)
    commands_df = read_tabular_file(commands_file)
    if commands_df.empty:
        return []
    commands = [str(value).strip() for value in commands_df.iloc[:, 0].dropna().tolist()]
    commands = [command for command in commands if command]
    logger.info("Loaded %s command(s)", len(commands))
    return commands


def normalize_blank(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def validate_devices(devices_df: pd.DataFrame, shared_password: str | None = None, require_password: bool = True) -> pd.DataFrame:
    missing = [column for column in REQUIRED_DEVICE_COLUMNS if column not in devices_df.columns]
    if missing:
        raise ValueError("Devices file is missing required column(s): " + ", ".join(missing))

    cleaned = devices_df.copy().dropna(how="all")
    if PASSWORD_COLUMN not in cleaned.columns:
        cleaned[PASSWORD_COLUMN] = ""

    for column in REQUIRED_DEVICE_COLUMNS + [PASSWORD_COLUMN]:
        cleaned[column] = cleaned[column].map(normalize_blank)

    if shared_password:
        cleaned.loc[cleaned[PASSWORD_COLUMN] == "", PASSWORD_COLUMN] = shared_password

    required_now = REQUIRED_DEVICE_COLUMNS + ([PASSWORD_COLUMN] if require_password else [])
    empty_rows = (cleaned[required_now] == "").any(axis=1)
    if empty_rows.any():
        bad_indexes = [str(index + 2) for index in cleaned.index[empty_rows].tolist()]
        raise ValueError(
            "Devices file has blank required values on spreadsheet row(s): "
            + ", ".join(bad_indexes)
            + f". Fill {PASSWORD_COLUMN}, set {DEFAULT_PASSWORD_ENV}, or use --prompt-password."
        )

    return cleaned


def sanitize_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe.strip("._") or "device"


def device_params_from_row(device_info: pd.Series, timeout: int) -> dict[str, object]:
    return {
        "device_type": str(device_info["Device Type"]).lower().replace(" ", "_"),
        "host": str(device_info["IP Address"]),
        "username": str(device_info["SSH Username"]),
        "password": str(device_info[PASSWORD_COLUMN]),
        "timeout": timeout,
    }


def execute_commands_on_device(
    device_info: pd.Series,
    commands: Iterable[str],
    output_dir: Path,
    timeout: int = 30,
    read_timeout: int = 60,
    dry_run: bool = False,
) -> dict[str, object]:
    hostname = str(device_info["Hostname"])
    ip_address = str(device_info["IP Address"])
    commands = list(commands)

    result = {
        "hostname": hostname,
        "ip": ip_address,
        "status": "failed",
        "output_file": "",
        "error": "",
        "commands": len(commands),
    }

    if dry_run:
        result["status"] = "dry_run"
        return result

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Connecting to %s (%s)", hostname, ip_address)

    try:
        from netmiko import ConnectHandler
    except ImportError as error:
        result["error"] = "Netmiko is not installed. Run: pip install -r requirements.txt"
        logger.error("%s", result["error"])
        return result

    connection = None
    try:
        connection = ConnectHandler(**device_params_from_row(device_info, timeout))
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = output_dir / f"{sanitize_filename(hostname)}_{sanitize_filename(ip_address)}_{timestamp}.txt"

        with filename.open("w", encoding="utf-8") as file:
            for index, command in enumerate(commands, start=1):
                logger.info("%s: running command %s/%s", hostname, index, len(commands))
                file.write(f"\n### Command {index}: {command}\n")
                try:
                    output = connection.send_command(command, read_timeout=read_timeout)
                    file.write(output)
                    if not output.endswith("\n"):
                        file.write("\n")
                except Exception as command_error:
                    message = f"ERROR executing {command!r}: {command_error}"
                    logger.error("%s", message)
                    file.write(message + "\n")
                file.write("#" * 72 + "\n")

        result.update({"status": "success", "output_file": str(filename)})
        logger.info("Completed %s", hostname)
        return result
    except Exception as error:
        result["error"] = str(error)
        logger.error("ERROR - %s (%s): %s", hostname, ip_address, error)
        return result
    finally:
        if connection is not None:
            try:
                connection.disconnect()
            except Exception:
                logger.debug("Disconnect failed for %s", hostname, exc_info=True)


def save_reports(results: list[dict[str, object]], output_dir: Path) -> dict[str, str | None]:
    report_dir = output_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    json_file = report_dir / f"run_summary_{stamp}.json"
    csv_file = report_dir / f"run_summary_{stamp}.csv"
    failed_file = report_dir / f"failed_devices_{stamp}.txt"

    with json_file.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=2)

    with csv_file.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["hostname", "ip", "status", "commands", "output_file", "error"])
        writer.writeheader()
        writer.writerows(results)

    failed = [item for item in results if item.get("status") == "failed"]
    failed_path: str | None = None
    if failed:
        with failed_file.open("w", encoding="utf-8") as file:
            file.write("FAILED DEVICES REPORT\n")
            file.write("=" * 40 + "\n")
            file.write(f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            file.write(f"Total Failed: {len(failed)}\n")
            file.write("=" * 40 + "\n\n")
            for item in failed:
                file.write(f"Hostname: {item['hostname']}\n")
                file.write(f"IP Address: {item['ip']}\n")
                file.write(f"Reason: {item['error']}\n")
                file.write("-" * 40 + "\n")
        failed_path = str(failed_file)

    return {"json_report": str(json_file), "csv_report": str(csv_file), "failed_report": failed_path}


def run_inventory(
    devices_file: Path,
    commands_file: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    workers: int = 1,
    timeout: int = 30,
    read_timeout: int = 60,
    dry_run: bool = False,
    shared_password: str | None = None,
) -> dict[str, object]:
    capture_dir = output_dir / "device_captures"
    logger.info("Network automation run started")
    devices_df = validate_devices(read_tabular_file(devices_file), shared_password=shared_password, require_password=not dry_run)
    commands = read_commands(commands_file)
    if not commands:
        raise ValueError("No commands found in the command file")

    rows = [row for _, row in devices_df.iterrows()]
    workers = max(1, min(int(workers), len(rows)))
    results: list[dict[str, object]] = []

    if workers == 1:
        for index, device_row in enumerate(rows, start=1):
            logger.info("Processing device %s/%s: %s", index, len(rows), device_row["Hostname"])
            results.append(execute_commands_on_device(device_row, commands, capture_dir, timeout, read_timeout, dry_run))
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(execute_commands_on_device, device_row, commands, capture_dir, timeout, read_timeout, dry_run): device_row
                for device_row in rows
            }
            for future in as_completed(future_map):
                results.append(future.result())

    reports = save_reports(results, output_dir)
    total = len(results)
    successful = sum(1 for item in results if item["status"] in {"success", "dry_run"})
    failed = sum(1 for item in results if item["status"] == "failed")
    success_rate = (successful / total) * 100 if total else 0.0

    summary = {
        "total": total,
        "successful": successful,
        "failed": failed,
        "success_rate": round(success_rate, 2),
        "workers": workers,
        "dry_run": dry_run,
        "output_dir": str(output_dir),
        **reports,
    }
    logger.info("Automation completed: %s", summary)
    return summary


def resolve_shared_password(env_name: str, prompt_password: bool) -> str | None:
    password = os.getenv(env_name)
    if password:
        return password
    if prompt_password:
        return getpass.getpass("SSH password for blank device rows: ")
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run network show commands from a device inventory file.")
    parser.add_argument("--devices", required=True, type=Path, help="Path to devices CSV/XLSX")
    parser.add_argument("--commands", required=True, type=Path, help="Path to commands CSV/XLSX")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Where captures, reports, and logs are written")
    parser.add_argument("--workers", type=int, default=1, help="Parallel device sessions. Start low, for example 3 to 5.")
    parser.add_argument("--timeout", type=int, default=30, help="Netmiko connection timeout in seconds")
    parser.add_argument("--read-timeout", type=int, default=60, help="Per-command read timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and write reports without connecting to devices")
    parser.add_argument("--password-env", default=DEFAULT_PASSWORD_ENV, help="Environment variable used for blank SSH Password values")
    parser.add_argument("--prompt-password", action="store_true", help="Prompt once for blank SSH Password values")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.output_dir / "logs", verbose=args.verbose)
    shared_password = resolve_shared_password(args.password_env, args.prompt_password)
    summary = run_inventory(
        args.devices,
        args.commands,
        args.output_dir,
        workers=args.workers,
        timeout=args.timeout,
        read_timeout=args.read_timeout,
        dry_run=args.dry_run,
        shared_password=shared_password,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
