"""Parsing and validation of the host report the Jarvis Mac sends.

No Home Assistant imports here, so the unit tests can load this file on their own.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

MAX_UPDATES = 20
MAX_TEXT = 200
# A host that has not reported for this long counts as not reporting. The script runs every
# 5 minutes, so this tolerates two missed runs.
STALE_AFTER = timedelta(minutes=15)

_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_MAX_EPOCH = 4102444800  # 2100-01-01


class ReportError(ValueError):
    """The payload is not a valid host report."""


@dataclass(frozen=True)
class HostReport:
    """One validated report. Optional values are None when the Mac did not send them."""

    reported_at: datetime
    hostname: str
    macos_version: str
    hardware_model: str
    boot_time: Optional[datetime]
    cpu_percent: Optional[float]
    cpu_cores: Optional[int]
    load_1m: Optional[float]
    load_5m: Optional[float]
    load_15m: Optional[float]
    memory_used_percent: Optional[float]
    disk_free_gb: Optional[float]
    disk_free_percent: Optional[float]
    vm_running: Optional[bool]
    filevault_on: Optional[bool]
    updates_count: Optional[int]
    updates_checked: Optional[datetime]
    updates: tuple


def _time(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise ReportError(f"{name} must be a UTC time like 2026-11-09T20:53:53Z")
    try:
        return datetime.strptime(value, _TIME_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError as err:
        raise ReportError(f"{name} must be a UTC time like 2026-11-09T20:53:53Z") from err


def _number(payload: dict, key: str, low: float, high: float) -> Optional[float]:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReportError(f"{key} must be a number")
    if not math.isfinite(value) or not low <= value <= high:
        raise ReportError(f"{key} is out of range")
    return float(value)


def _integer(payload: dict, key: str, low: int, high: int) -> Optional[int]:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReportError(f"{key} must be a whole number")
    if not low <= value <= high:
        raise ReportError(f"{key} is out of range")
    return value


def _flag(payload: dict, key: str) -> Optional[bool]:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ReportError(f"{key} must be true or false")
    return value


def _text(payload: dict, key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ReportError(f"{key} must be text")
    return value.strip()[:MAX_TEXT]


def parse_report(payload: Any) -> HostReport:
    """Validate a decoded JSON payload; raise ReportError when it is not a host report."""
    if not isinstance(payload, dict):
        raise ReportError("the report must be a JSON object")
    if "reported_at" not in payload:
        raise ReportError("reported_at is missing")

    boot_time = None
    if payload.get("boot_time") is not None:
        boot_time = _time(payload["boot_time"], "boot_time")

    checked = None
    epoch = _integer(payload, "updates_checked_epoch", 0, _MAX_EPOCH)
    if epoch is not None:
        checked = datetime.fromtimestamp(epoch, tz=timezone.utc)

    raw_updates = payload.get("updates", [])
    if not isinstance(raw_updates, list) or len(raw_updates) > MAX_UPDATES:
        raise ReportError("updates must be a list of at most %d labels" % MAX_UPDATES)
    if not all(isinstance(label, str) for label in raw_updates):
        raise ReportError("updates must be a list of text labels")
    updates = tuple(label.strip()[:MAX_TEXT] for label in raw_updates if label.strip())

    return HostReport(
        reported_at=_time(payload["reported_at"], "reported_at"),
        hostname=_text(payload, "hostname"),
        macos_version=_text(payload, "macos_version"),
        hardware_model=_text(payload, "hardware_model"),
        boot_time=boot_time,
        cpu_percent=_number(payload, "cpu_percent", 0, 100),
        cpu_cores=_integer(payload, "cpu_cores", 1, 4096),
        load_1m=_number(payload, "load_1m", 0, 100000),
        load_5m=_number(payload, "load_5m", 0, 100000),
        load_15m=_number(payload, "load_15m", 0, 100000),
        memory_used_percent=_number(payload, "memory_used_percent", 0, 100),
        disk_free_gb=_number(payload, "disk_free_gb", 0, 1e9),
        disk_free_percent=_number(payload, "disk_free_percent", 0, 100),
        vm_running=_flag(payload, "vm_running"),
        filevault_on=_flag(payload, "filevault_on"),
        updates_count=_integer(payload, "updates_count", 0, 10000),
        updates_checked=checked,
        updates=updates,
    )


def is_fresh(received_at: Optional[datetime], now: datetime) -> bool:
    """True when a report arrived recently enough. Uses Home Assistant's receive time, so a
    wrong clock on the Mac cannot make a host look alive or dead."""
    return received_at is not None and now - received_at <= STALE_AFTER


def latest_macos_version(labels: tuple) -> Optional[str]:
    """The version of the first pending macOS update ("macOS 27.2.1-26B131" gives "27.2.1"),
    or None when no pending update is a macOS one (for example only Command Line Tools)."""
    for label in labels:
        if label.lower().startswith("macos"):
            match = re.search(r"(\d+(?:\.\d+)+)", label)
            if match:
                return match.group(1)
    return None
