# Quick Start Guide

## What Changed?

### ✅ Fixed: Rig Connection Detection
**Before**: Showed "Rig: Connected" even without a rig
**Now**: Only shows connected when a real rig is responding

### ✨ New: Reconnect Button
Gold button to help you reconnect your rig with step-by-step instructions

## Installation

```bash
# Install dependencies (if not already installed)
pip install psutil

# Run the app
./cw_companion_enhanced.py
```

## Testing Rig Detection

Run the test script to see what your rig returns:

```bash
./test_rig_connection.py
```

This will show you:
- Transceiver name
- Frequency value
- Whether detection logic thinks rig is connected
- Why it made that determination

## Expected Status Display

### With Rig Connected:
```
Status: Process: Running | XML-RPC: Connected (v1.4.7) | Rig: Connected (FT-710)
Frequency: 14.025 MHz | Mode: CW | Band: 20m | Rig: FT-710
```

### Without Rig:
```
Status: Process: Running | XML-RPC: Connected (v1.4.7) | Rig: Not connected
Frequency: --- (No rig) | Mode: --- | Band: --- | Rig: Not connected
```

## How Rig Detection Works

The app checks TWO things every 3 seconds:

1. **Transceiver name** (`rig.get_xcvr()`)
   - Must not be empty
   - Must not be "NONE"
   
2. **Frequency** (`rig.get_vfo()`)
   - Must be between 100 kHz and 60 MHz
   - Verifies rig is actually responding

Both must pass for status to show "Connected"

## Using the Reconnect Button

1. Notice "Rig: Not connected" status
2. Check physical connections:
   - Rig powered on?
   - USB/serial cable connected?
3. Click the gold **"Reconnect Rig"** button
4. Follow the instructions in the dialog
5. In flrig: Config → Initialize
6. Status updates within 3 seconds

## Troubleshooting

### Test shows rig not connected but flrig shows connected

Try these flrig commands:
1. Config → Initialize
2. Wait 10 seconds
3. Run test script again

### Frequency shows 0.000 MHz

Your rig might need initialization:
1. In flrig: Config → Initialize
2. Or: File → Config → Init

### Connection keeps dropping

Check:
- USB cable quality (try a different cable)
- USB port (try a different port)
- RF interference near USB cable
- Ground loops

## Files Included

- `cw_companion_enhanced.py` - Main application
- `test_rig_connection.py` - Test script for rig detection
- `requirements.txt` - Python dependencies
- `README.md` - Full documentation
- `CHANGELOG.md` - Detailed changes
- This file - Quick start guide

## Need Help?

1. Run `./test_rig_connection.py` to diagnose
2. Check flrig's Config menu
3. Verify rig is powered and connected
4. Try restarting flrig

73 de DA1BB!
