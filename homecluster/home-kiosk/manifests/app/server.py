"""Floor plan kiosk for the iOS 12 iPad.

Home Assistant's own frontend no longer parses on iOS 12 (its legacy build
ships BigInt literals), so this serves a plain ES5 page and proxies a small,
fixed slice of the HA REST API. The HA token stays in the cluster: the page can
read only the entities below and toggle only the lights below.
"""

import hashlib
import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HA_URL = os.environ.get("HA_URL", "http://home-assistant.default.svc.cluster.local:8123").rstrip("/")
HA_TOKEN = os.environ["HA_TOKEN"]
APP_DIR = os.environ.get("APP_DIR", "/app")
IMAGE_DIR = os.environ.get("IMAGE_DIR", "/images")
PORT = int(os.environ.get("PORT", "8080"))
CACHE_SECONDS = 1.0

LIGHTS = {
    "kitchen": "light.kitchen_kitchen_main_lights",
    "living_room": "light.living_room_living_room_main_lights",
}
SENSORS = {
    "upstairs_hallway": ("sensor.upstairs_hallway_current_temperature", "sensor.upstairs_hallway_current_humidity"),
    "living_room": ("sensor.living_room_current_temperature", "sensor.living_room_current_humidity"),
    "downstairs_hallway": ("sensor.downstairs_hallway_current_temperature", "sensor.downstairs_hallway_current_humidity"),
}
WEATHER = "weather.forecast_home"
SUN = "sun.sun"

# Images are cached for a day, so their URLs carry a content hash.
def _image_version():
    h = hashlib.sha1()
    for name in sorted(os.listdir(IMAGE_DIR)):
        if name.endswith(".jpg"):
            with open(os.path.join(IMAGE_DIR, name), "rb") as f:
                h.update(f.read())
    return h.hexdigest()[:10]


IMAGE_VERSION = _image_version()

_cache = {"at": 0.0, "body": None}
_cache_lock = threading.Lock()


def ha(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        HA_URL + path,
        data=data,
        method=method,
        headers={"Authorization": "Bearer " + HA_TOKEN, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read() or b"null")


def sensor_text(state):
    if not state or state["state"] in ("unknown", "unavailable"):
        return None
    unit = state["attributes"].get("unit_of_measurement", "")
    return state["state"] + (" " + unit if unit else "")


def snapshot():
    states = {s["entity_id"]: s for s in ha("GET", "/api/states")}
    weather = states.get(WEATHER) or {"state": None, "attributes": {}}
    attrs = weather["attributes"]
    return {
        "night": (states.get(SUN) or {}).get("state") == "below_horizon",
        "lights": {zone: (states.get(eid) or {}).get("state") for zone, eid in LIGHTS.items()},
        "sensors": {
            room: {"temperature": sensor_text(states.get(t)), "humidity": sensor_text(states.get(h))}
            for room, (t, h) in SENSORS.items()
        },
        "weather": {
            "condition": weather["state"],
            "temperature": attrs.get("temperature"),
            "temperature_unit": attrs.get("temperature_unit", "°C"),
            "humidity": attrs.get("humidity"),
            "wind_speed": attrs.get("wind_speed"),
            "wind_speed_unit": attrs.get("wind_speed_unit", "km/h"),
        },
    }


def cached_snapshot():
    with _cache_lock:
        if _cache["body"] is None or time.monotonic() - _cache["at"] > CACHE_SECONDS:
            _cache["body"] = json.dumps(snapshot()).encode()
            _cache["at"] = time.monotonic()
        return _cache["body"]


def find_image(name):
    if "/" in name or not name.endswith(".jpg"):
        return None
    path = os.path.join(IMAGE_DIR, name)
    return path if os.path.isfile(path) else None


class Handler(BaseHTTPRequestHandler):
    server_version = "home-kiosk"

    def send(self, code, body, content_type, cache="no-store"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            with open(os.path.join(APP_DIR, "index.html"), "rb") as f:
                page = f.read().replace(b"__IMAGE_VERSION__", IMAGE_VERSION.encode())
            return self.send(200, page, "text/html; charset=utf-8")
        if path == "/healthz":
            return self.send(200, b"ok", "text/plain")
        if path == "/api/state":
            try:
                return self.send(200, cached_snapshot(), "application/json")
            except Exception as e:  # HA down or token rejected: the page shows "offline"
                self.log_error("state: %r", e)
                return self.send(502, b'{"error":"home assistant unreachable"}', "application/json")
        if path.startswith("/img/"):
            image = find_image(path[len("/img/"):])
            if image:
                with open(image, "rb") as f:
                    return self.send(200, f.read(), "image/jpeg", "public, max-age=86400")
        self.send(404, b"not found", "text/plain")

    do_HEAD = do_GET

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        zone = path[len("/api/toggle/"):] if path.startswith("/api/toggle/") else None
        if zone not in LIGHTS:
            return self.send(404, b"not found", "text/plain")
        try:
            ha("POST", "/api/services/light/toggle", {"entity_id": LIGHTS[zone]})
        except Exception as e:
            self.log_error("toggle %s: %r", zone, e)
            return self.send(502, b'{"error":"toggle failed"}', "application/json")
        with _cache_lock:
            _cache["body"] = None
        self.send(200, b'{"ok":true}', "application/json")

    def log_message(self, fmt, *args):
        if not self.path.startswith(("/api/state", "/healthz")):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
