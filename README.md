# EVCC surplus → Wolf SG Ready

A small Raspberry Pi web service that controls a Shelly connected to a Wolf heat pump's SG Ready input.

The service evaluates every 15 minutes (configurable) and switches SG Ready on only when:

- battery state of charge is at least the configured minimum (default: 50%), and
- solar surplus is at least the configured minimum (default: 1.8 kW).

At the configured daily cutoff (default: 17:00 Europe/Berlin), the scheduler stops and the Shelly is forced off.

## Quick start

    python3 -m venv .venv
    . .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env
    python app.py

Open http://raspberry-pi:8080 and enter the EVCC URL/token and Shelly details. Settings are stored in data/config.json.

## EVCC data mapping

By default the service reads batterySoc, gridPower, and housePower from EVCC's /api/state response. Configure JSON paths and units in the UI. Values are expected in kW; set the scale to 1000 if your endpoint returns watts.

## Shelly support

Gen1 relay HTTP and Gen2/Plus/Pro JSON-RPC are supported.

## Safety

Network errors fail safe by switching the Shelly off. Verify Wolf SG Ready wiring and polarity before enabling automatic control.
