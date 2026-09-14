# EVCC surplus → Wolf SG Ready

A small Raspberry Pi web service that controls a Shelly connected to a Wolf heat pump's SG Ready input.

The service evaluates every 15 minutes (configurable) and switches SG Ready on only when:

- battery state of charge is at least the configured minimum (default: 50%), and
- solar surplus is at least the configured minimum (default: 1.8 kW).

At the configured daily cutoff (default: 17:00 Europe/Berlin), the scheduler stops and the Shelly is forced off. The cutoff is also enforced immediately after every evaluation, so a restart cannot leave SG Ready on after the cutoff.

## Important energy-unit note

The threshold is represented as **kW**, because EVCC's live power values are instantaneous power. The default `1.8` therefore means 1.8 kW (not 1.8 kWh). If your EVCC endpoint exposes energy rather than power, use its mapping/adapter or adjust the integration before deploying.

## Quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open `http://raspberry-pi:8090` and enter the EVCC URL/token (if needed) and Shelly details. Settings are stored in `data/config.json`.

## EVCC data mapping

By default the service reads `batterySoc`, `gridPower`, and `housePower` from EVCC's `/api/state` response. It calculates surplus as `housePower - gridPower` when grid import is positive and solar export is negative. For installations where field names differ, use the advanced JSON-path fields in the UI. Dot paths also understand array indexes, for example `result.site.battery.soc`.

You can instead map a direct surplus field. Sign convention is normalized: positive surplus means power available for the heat pump. Values are expected in kW; set the scale to `1000` if your endpoint returns watts.

## Shelly support

- Gen1: `http://SHELLY_IP/relay/0?turn=on|off`
- Gen2/Plus/Pro: JSON-RPC `http://SHELLY_IP/rpc/Switch.Set` with `{"id":0,"on":true|false}`

The UI lets you select the generation, relay/channel, and optional auth credentials.

## Run as a systemd service

```bash
sudo mkdir -p /opt/evcc-sg-ready
sudo cp -r . /opt/evcc-sg-ready
sudo cp deploy/evcc-sg-ready.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now evcc-sg-ready
```

The service runs as the current `User=` from the unit file; change it and `WorkingDirectory=` if you use another install path.

## Safety

The default state is off. Network errors fail safe by switching the Shelly off. Use a dedicated Shelly relay and verify Wolf's SG Ready wiring and polarity before enabling automatic control.
