# Jarvis Host

A Home Assistant custom integration that shows the Mac running Home Assistant as a device, with
sensors for its health: CPU load, memory, free disk space, last boot, whether the Home Assistant
VM is running, FileVault, and pending macOS updates.

It never connects to the Mac. The Mac runs a small script that posts a JSON report to a
Home Assistant webhook every few minutes. This is part of my Jarvis
setup (Home Assistant OS on a Mac mini), but any program can send the report.

## Status

Version 0.1.0. The unit tests and a set of tests inside a real Home Assistant (setup flow,
webhook, device, entities, restore, stale detection) pass against Home Assistant 2026.2.
It has not yet been run in a long-lived installation, and hassfest and HACS validation only run
in CI on GitHub.

## Install

1. Settings → **Marketplace** → **Add from link** → `martijnkoot/ha-jarvis-host`. Older Home
   Assistant versions can use [HACS](https://hacs.xyz) with the same repository.
2. Install **Jarvis Host** and restart Home Assistant when asked.
3. Settings → Devices & services → **Add integration** → *Jarvis Host*. Give the Mac a name
   (for example *Mac mini*); the next step shows the webhook address.
4. Put that address in the settings of the script on the Mac (`WEBHOOK_URL=`). The address is
   shown again under the integration's **Configure** button.

Add the integration again for a second Mac.

If you reach Home Assistant through a proxy or on another port, the address shown may need its
host or port changed to match how the Mac reaches Home Assistant.

## What you get

One device, named as you chose, with manufacturer Apple, the model the Mac reports (or the one
you typed) and the macOS version.

| Entity | Notes |
|---|---|
| `sensor` CPU | Percent in use; the number of cores is an attribute |
| `sensor` Load | 1 minute load average; 5 and 15 minutes are attributes |
| `sensor` Memory used, Disk free, Disk free percentage | |
| `sensor` Pending updates | Count; the labels and the time of the last check are attributes |
| `update` macOS | Installed version against the pending macOS version. It only reports; install on the Mac |
| `binary_sensor` Reporting | On while reports keep coming (see below) |
| `binary_sensor` Home Assistant VM | The QEMU process is running |
| `binary_sensor` FileVault (diagnostic) | Should be off on a Mac that has to start without a login |
| `sensor` Last boot, Last report (diagnostic) | |

**Reporting and unavailable.** The time of the last report is Home Assistant's own receive time.
When no report has arrived for 15 minutes, *Reporting* turns off and every other entity becomes
unavailable instead of showing old values as if they were current. Values are kept over a Home
Assistant restart, so a restart does not blank them.

If the whole Mac is down, Home Assistant is down too, so this cannot tell you that. Pair it with
an external check: have the script ping a service such as healthchecks.io after each accepted
report.

## The report

`POST` JSON to the webhook. Only `reported_at` is required; every other field may be missing or
`null`, and a report with a wrong type or an out-of-range value is rejected with HTTP 400 and
ignored.

```json
{
  "reported_at": "2026-11-09T20:53:53Z",
  "hostname": "Mac-mini",
  "macos_version": "27.2",
  "hardware_model": "Mac16,10",
  "boot_time": "2026-10-27T16:24:21Z",
  "cpu_percent": 3.7,
  "cpu_cores": 14,
  "load_1m": 2.88,
  "load_5m": 2.25,
  "load_15m": 2.27,
  "memory_used_percent": 42,
  "disk_free_gb": 531.1,
  "disk_free_percent": 57.3,
  "vm_running": true,
  "filevault_on": true,
  "updates_count": 1,
  "updates": ["macOS 27.2.1-26B131"],
  "updates_checked_epoch": 1794257893
}
```

Times are UTC in the form shown. `updates` holds at most 20 labels; a label starting with
`macOS` followed by a version (`macOS 27.2.1-26B131`) makes the update entity show 27.2.1 as the
newer version.

A webhook answers HTTP 200 even for an unknown id, and a rejected report answers 400. Whatever
sends the report should check the entities, not only the status code, when setting up.

## Security

The webhook accepts requests from the local network only, and the address is the secret. There is
no way to send anything back to the Mac, and the integration cannot change anything on it.

## Development

```bash
python3 -m unittest discover -s tests -v          # report parser, no Home Assistant needed
pip install pytest-homeassistant-custom-component  # then, in a Python 3.13 environment:
pytest -q                                          # tests inside a real Home Assistant
```

## License

MIT
