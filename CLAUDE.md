# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Install dependencies
pip install PyQt5 psutil

# Run
python3 hambuddy.py
```

There are no automated tests or linter configuration in this project.

## Architecture

The entire application lives in a single file: `hambuddy.py` (~2880 lines).

### Classes

- **`DXClusterWorker(QObject)`** — Background worker that connects via Telnet to a DX spotting cluster, reads and parses incoming spot lines, and emits Qt signals (`spot_received`, `connection_status`). Runs in a dedicated `QThread`.
- **`DXClusterDialog(QDialog)`** — Settings dialog for DX cluster host/port/callsign, with a preset list of known clusters.
- **`SettingsDialog(QDialog)`** — Settings dialog for frequency tolerances (manual lock ±kHz, auto-search ±kHz) and DX cluster defaults.
- **`CWCompanion(QMainWindow)`** — The main window. Owns all state, timers, and business logic.

### External Process Integration

The app launches and monitors three external programs as subprocesses:

| Program | Purpose | Communication |
|---------|---------|---------------|
| **flrig** | Radio control | XML-RPC at `localhost:12345` via `xmlrpc.client` |
| **qlog** | Ham radio logging | Reads SQLite DB at `~/.config/qlog/qlog.db` |
| **hamclock** | Amateur radio clock display | Subprocess only (no IPC) |

Polling timers in `CWCompanion.__init__` drive all monitoring:
- `connection_timer` → `check_flrig_connection()` — XML-RPC heartbeat
- `process_monitor_timer` → `monitor_flrig_process()` — subprocess liveness via `psutil`
- `rig_connection_timer` → `monitor_rig_connection()` — verifies actual rig (xcvr name + VFO frequency)
- `freq_monitor_timer` → `monitor_frequency()` — polls VFO and matches against DX spot cache
- `qlog_monitor_timer` / `hamclock_monitor_timer` — subprocess liveness for qlog/hamclock

### Configuration Files

- `~/.config/cw_companion/config.ini` — Station callsign (legacy INI format)
- `~/.config/cw_companion/settings.json` — Frequency tolerances and DX cluster defaults

### Key Data Flows

1. **Rig frequency → spot matching**: `monitor_frequency()` reads VFO via XML-RPC, caches spots by frequency in `self.spot_cache`, calls `check_spot_match()` to find a spot within `search_tolerance_khz`, and populates the CW exchange panel via `load_welcome_screen()`.
2. **Manual callsign**: User can type a callsign directly; `load_manual_callsign()` sets `manually_selected_spot` and calls `load_welcome_screen()` with that callsign, locking to the current VFO frequency within `lock_tolerance_khz`.
3. **DX spots**: `DXClusterWorker` emits `spot_received` → `on_cluster_spot()` updates `self.dx_spots` and `self.spot_cache`, and inserts rows into the all-spots and filtered-spots tables.
