# HamBuddy

A desktop companion application for amateur radio CW (Morse code) operations. Built with Python/PyQt5, it integrates with **flrig**, **qlog**, and **hamclock** and provides real-time DX cluster spot matching with CW exchange templates.

## Features

- **Subprocess management** — start, stop, and monitor flrig, qlog, and hamclock from a single UI
- **Rig monitoring** — connects to flrig via XML-RPC, polls VFO frequency and rig status every few seconds
- **DX cluster** — telnet connection to any DX spotting cluster with band and WPM filtering
- **Spot matching** — automatically matches the current VFO frequency to incoming DX spots (configurable tolerance)
- **CW exchange templates** — color-coded QSO scripts for Normal, SOTA, POTA, and Contest operating styles, in both calling and answering directions
- **Country lookup** — resolves callsign prefix to country/QTH

## Requirements

- Python 3
- [flrig](http://www.w1hkj.com/flrig-help/) — radio control software (must be installed separately)
- [qlog](https://github.com/foldynl/qlog) — logging software (optional)
- [hamclock](https://www.clearskyinstitute.com/ham/HamClock/) — ham radio clock (optional)

```bash
pip install PyQt5 psutil
```

## Usage

```bash
python3 hambuddy.py
```

On first run, enter your callsign in the settings. The app saves configuration to `~/.config/cw_companion/`.

### Typical workflow

1. Click **Start flrig** — launches flrig and connects via XML-RPC at `localhost:12345`
2. Connect to a **DX cluster** (cluster tab) to receive live spots
3. Tune your rig — the app detects when your VFO matches a spot and loads the CW exchange template
4. Or type a callsign manually to load a template without a spot match

### Rig detection

The app considers a rig "connected" only when both conditions are true:
- `rig.get_xcvr()` returns a non-empty name that is not `"NONE"`
- `rig.get_vfo()` returns a frequency between 100 kHz and 60 MHz

### Frequency matching tolerances (configurable in Settings)

| Mode | Default | Purpose |
|------|---------|---------|
| Auto-search | ±5 kHz | Matching incoming DX spots to VFO |
| Manual lock | ±1 kHz | Keeping a manually selected spot active while tuning |

## Configuration files

| Path | Contents |
|------|----------|
| `~/.config/cw_companion/config.ini` | Station callsign |
| `~/.config/cw_companion/settings.json` | Frequency tolerances, DX cluster host/port/callsign |

## Supported DX clusters

The app ships with presets for several free clusters including the Reverse Beacon Network (RBN) and several DXSpider nodes. Any Telnet-accessible DX cluster can be used with the Custom option.

---

73 de DA1BB
