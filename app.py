import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from flask import Flask, flash, redirect, render_template, request, url_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("evcc-sg-ready")

ROOT = Path(__file__).parent
CONFIG_FILE = Path(os.getenv("CONFIG_FILE", ROOT / "data/config.json"))
DEFAULTS = {
    "evcc_url": "http://evcc.local",
    "evcc_token": "",
    "battery_soc_path": "batterySoc",
    "battery_soc_scale": 1,
    "surplus_path": "",
    "grid_power_path": "gridPower",
    "house_power_path": "housePower",
    "power_scale": 1,
    "battery_min_soc": 50,
    "surplus_min_kw": 1.8,
    "interval_minutes": 15,
    "cutoff_time": "17:00",
    "timezone": "Europe/Berlin",
    "shelly_url": "http://shelly.local",
    "shelly_generation": "gen2",
    "shelly_channel": 0,
    "shelly_username": "",
    "shelly_password": "",
    "enabled": True,
}

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret")
state = {"sg_ready": False, "last_check": None, "last_reason": "Not checked yet", "last_values": {}}
state_lock = threading.Lock()


def load_config():
    try:
        with CONFIG_FILE.open() as f:
            saved = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        saved = {}
    return {**DEFAULTS, **saved}


def save_config(config):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2) + "\n")
    tmp.replace(CONFIG_FILE)


def value_at(payload, path):
    value = payload
    for part in path.strip(".").split("."):
        if not part:
            continue
        if isinstance(value, list):
            value = value[int(part)]
        else:
            value = value[part]
    return float(value)


def fetch_evcc(config):
    url = urljoin(config["evcc_url"].rstrip("/") + "/", "api/state")
    headers = {"Authorization": f"Bearer {config['evcc_token']}"} if config["evcc_token"] else {}
    response = requests.get(url, headers=headers, timeout=8)
    response.raise_for_status()
    payload = response.json()
    soc = value_at(payload, config["battery_soc_path"]) / float(config["battery_soc_scale"])
    scale = float(config["power_scale"])
    if config["surplus_path"].strip():
        surplus = value_at(payload, config["surplus_path"]) / scale
    else:
        grid = value_at(payload, config["grid_power_path"]) / scale
        house = value_at(payload, config["house_power_path"]) / scale
        # EVCC commonly reports grid export as negative; house - grid gives export surplus.
        surplus = house - grid
    return {"battery_soc": soc, "surplus_kw": surplus}


def shelly_set(config, on):
    base = config["shelly_url"].rstrip("/")
    auth = (config["shelly_username"], config["shelly_password"]) if config["shelly_username"] else None
    if config["shelly_generation"] == "gen1":
        url = f"{base}/relay/{int(config['shelly_channel'])}"
        response = requests.get(url, params={"turn": "on" if on else "off"}, auth=auth, timeout=8)
    else:
        url = f"{base}/rpc/Switch.Set"
        response = requests.post(url, json={"id": int(config["shelly_channel"]), "on": bool(on)}, auth=auth, timeout=8)
    response.raise_for_status()


def after_cutoff(config):
    now = datetime.now(ZoneInfo(config["timezone"]))
    hour, minute = (int(x) for x in config["cutoff_time"].split(":", 1))
    return (now.hour, now.minute) >= (hour, minute)


def evaluate():
    config = load_config()
    try:
        if not config["enabled"]:
            shelly_set(config, False)
            reason = "Automation disabled"
            values = {}
        elif after_cutoff(config):
            shelly_set(config, False)
            reason = f"Daily cutoff reached ({config['cutoff_time']})"
            values = {}
        else:
            values = fetch_evcc(config)
            should_on = values["battery_soc"] >= float(config["battery_min_soc"]) and values["surplus_kw"] >= float(config["surplus_min_kw"])
            shelly_set(config, should_on)
            reason = "Conditions met" if should_on else "Conditions not met"
            with state_lock:
                state["sg_ready"] = should_on
        with state_lock:
            state["last_check"] = datetime.now().astimezone().isoformat(timespec="seconds")
            state["last_reason"] = reason
            state["last_values"] = values
    except Exception as exc:
        log.exception("Evaluation failed")
        try:
            shelly_set(config, False)
        except Exception:
            log.exception("Fail-safe Shelly off also failed")
        with state_lock:
            state.update(last_check=datetime.now().astimezone().isoformat(timespec="seconds"), last_reason=f"Error; forced off: {exc}", sg_ready=False)


def scheduler():
    while True:
        evaluate()
        minutes = max(1, int(load_config()["interval_minutes"]))
        time.sleep(minutes * 60)


@app.route("/", methods=["GET", "POST"])
def index():
    config = load_config()
    if request.method == "POST":
        for key in DEFAULTS:
            if key in {"enabled"}:
                config[key] = key in request.form
            elif key in request.form:
                config[key] = request.form[key]
        for key in ["battery_soc_scale", "power_scale", "battery_min_soc", "surplus_min_kw", "interval_minutes", "shelly_channel"]:
            try:
                config[key] = float(config[key]) if key != "shelly_channel" and key != "interval_minutes" else int(config[key])
            except ValueError:
                flash(f"Invalid value for {key}", "error")
                return render_template("index.html", config=config, state=state)
        save_config(config)
        flash("Settings saved. Running a check now.", "success")
        evaluate()
        return redirect(url_for("index"))
    with state_lock:
        current_state = dict(state)
    return render_template("index.html", config=config, state=current_state)


if __name__ == "__main__":
    threading.Thread(target=scheduler, daemon=True).start()
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8080")))
