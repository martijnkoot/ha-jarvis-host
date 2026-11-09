"""Tests for the report parser. Loads report.py by path, so Home Assistant is not needed."""

import copy
import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "custom_components" / "jarvis_host" / "report.py"
_SPEC = importlib.util.spec_from_file_location("jarvis_host_report", _PATH)
report = importlib.util.module_from_spec(_SPEC)
# dataclasses look the module up by name while the class is being built.
import sys  # noqa: E402

sys.modules["jarvis_host_report"] = report
_SPEC.loader.exec_module(report)

# A report as jarvis-host-report sends it.
SAMPLE = {
    "boot_time": "2026-10-27T16:24:21Z",
    "cpu_cores": 14,
    "cpu_percent": 3.7,
    "disk_free_gb": 531.1,
    "disk_free_percent": 57.3,
    "filevault_on": True,
    "hardware_model": "Mac16,10",
    "hostname": "Martijns-MacBook-Pro",
    "load_15m": 2.27,
    "load_1m": 2.88,
    "load_5m": 2.25,
    "macos_version": "27.2",
    "memory_used_percent": 42,
    "reported_at": "2026-11-09T20:53:53Z",
    "updates": ["macOS 27.2.1-26B131"],
    "updates_checked_epoch": 1794257893,
    "updates_count": 1,
    "vm_running": True,
}


def sample(**changes):
    payload = copy.deepcopy(SAMPLE)
    for key, value in changes.items():
        if value is ...:
            payload.pop(key, None)
        else:
            payload[key] = value
    return payload


class ParseReportTests(unittest.TestCase):
    def test_full_report(self):
        parsed = report.parse_report(SAMPLE)
        self.assertEqual(parsed.cpu_percent, 3.7)
        self.assertEqual(parsed.cpu_cores, 14)
        self.assertEqual(parsed.memory_used_percent, 42.0)
        self.assertEqual(parsed.macos_version, "27.2")
        self.assertEqual(parsed.hardware_model, "Mac16,10")
        self.assertTrue(parsed.vm_running)
        self.assertEqual(parsed.updates, ("macOS 27.2.1-26B131",))
        self.assertEqual(parsed.updates_count, 1)
        self.assertEqual(parsed.boot_time, datetime(2026, 10, 27, 16, 24, 21, tzinfo=timezone.utc))
        self.assertEqual(parsed.updates_checked.tzinfo, timezone.utc)

    def test_optional_values_may_be_missing_or_null(self):
        parsed = report.parse_report(
            {"reported_at": "2026-11-09T20:53:53Z", "updates_count": None, "cpu_percent": None}
        )
        self.assertIsNone(parsed.cpu_percent)
        self.assertIsNone(parsed.updates_count)
        self.assertIsNone(parsed.vm_running)
        self.assertEqual(parsed.updates, ())
        self.assertEqual(parsed.hardware_model, "")

    def test_updates_not_checked_yet(self):
        parsed = report.parse_report(sample(updates_count=None, updates_checked_epoch=None, updates=[]))
        self.assertIsNone(parsed.updates_count)
        self.assertIsNone(parsed.updates_checked)

    def test_rejects_what_is_not_a_report(self):
        for payload in (None, [], "text", 5, {}, {"cpu_percent": 5}):
            with self.assertRaises(report.ReportError, msg=repr(payload)):
                report.parse_report(payload)

    def test_rejects_bad_times(self):
        for bad in ("yesterday", "2026-11-09 20:53:53", 12345, None):
            with self.assertRaises(report.ReportError, msg=repr(bad)):
                report.parse_report(sample(reported_at=bad))
        with self.assertRaises(report.ReportError):
            report.parse_report(sample(boot_time="nope"))

    def test_rejects_bad_numbers(self):
        for key, bad in (
            ("cpu_percent", 101),
            ("cpu_percent", -1),
            ("cpu_percent", "50"),
            ("cpu_percent", True),
            ("cpu_percent", float("nan")),
            ("cpu_percent", float("inf")),
            ("memory_used_percent", 150),
            ("cpu_cores", 0),
            ("cpu_cores", 2.5),
            ("updates_count", -1),
            ("updates_count", True),
            ("updates_checked_epoch", 10**12),
        ):
            with self.assertRaises(report.ReportError, msg=f"{key}={bad!r}"):
                report.parse_report(sample(**{key: bad}))

    def test_rejects_bad_flags_and_text(self):
        with self.assertRaises(report.ReportError):
            report.parse_report(sample(vm_running="yes"))
        with self.assertRaises(report.ReportError):
            report.parse_report(sample(filevault_on=1))
        with self.assertRaises(report.ReportError):
            report.parse_report(sample(hostname=["x"]))

    def test_updates_limits(self):
        with self.assertRaises(report.ReportError):
            report.parse_report(sample(updates="macOS"))
        with self.assertRaises(report.ReportError):
            report.parse_report(sample(updates=["ok", 5]))
        with self.assertRaises(report.ReportError):
            report.parse_report(sample(updates=["x"] * (report.MAX_UPDATES + 1)))
        parsed = report.parse_report(sample(updates=["  macOS 27.3  ", "", "y" * 1000]))
        self.assertEqual(parsed.updates[0], "macOS 27.3")
        self.assertEqual(len(parsed.updates), 2)
        self.assertEqual(len(parsed.updates[1]), report.MAX_TEXT)

    def test_text_is_trimmed_and_capped(self):
        parsed = report.parse_report(sample(hostname="  " + "h" * 500))
        self.assertEqual(len(parsed.hostname), report.MAX_TEXT)


class FreshnessTests(unittest.TestCase):
    NOW = datetime(2026, 11, 9, 21, 0, 0, tzinfo=timezone.utc)

    def test_fresh_and_stale(self):
        self.assertTrue(report.is_fresh(self.NOW - timedelta(minutes=5), self.NOW))
        self.assertTrue(report.is_fresh(self.NOW - report.STALE_AFTER, self.NOW))
        self.assertFalse(report.is_fresh(self.NOW - report.STALE_AFTER - timedelta(seconds=1), self.NOW))

    def test_never_reported_is_not_fresh(self):
        self.assertFalse(report.is_fresh(None, self.NOW))


class LatestMacosVersionTests(unittest.TestCase):
    def test_version_from_label(self):
        self.assertEqual(report.latest_macos_version(("macOS 27.2.1-26B131",)), "27.2.1")
        self.assertEqual(report.latest_macos_version(("macOS Tahoe 27.3-26C100",)), "27.3")

    def test_skips_other_updates(self):
        labels = ("Command Line Tools for Xcode-26.2", "macOS 27.2.1-26B131")
        self.assertEqual(report.latest_macos_version(labels), "27.2.1")

    def test_none_without_macos_update(self):
        self.assertIsNone(report.latest_macos_version(()))
        self.assertIsNone(report.latest_macos_version(("Command Line Tools for Xcode-26.2",)))
        self.assertIsNone(report.latest_macos_version(("macOS without a version",)))


if __name__ == "__main__":
    unittest.main()
