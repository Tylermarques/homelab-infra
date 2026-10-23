"""Time-limited public links to Immich albums over Tailscale Funnel.

Each share is an Immich shared link for one album, recorded in the
`immich-share-state` ConfigMap with its name and expiry. All shares are served
through one Tailscale Ingress (`share-funnel`, managed in git) in front of
Immich Public Proxy. This service turns Funnel on for that Ingress while at
least one share is active and off once none are, so the public hostname only
resolves while something is shared. A background loop deletes each Immich
link once its expiry passes.

Stdlib only, so it runs on the stock python image.
"""

import datetime as dt
import html
import json
import os
import re
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IMMICH_URL = os.environ["IMMICH_URL"].rstrip("/")
IMMICH_API_KEY = os.environ["IMMICH_API_KEY"]
NAMESPACE = os.environ["NAMESPACE"]
FUNNEL_INGRESS = os.environ.get("FUNNEL_INGRESS", "share-funnel")
STATE_CONFIGMAP = os.environ.get("STATE_CONFIGMAP", "immich-share-state")
MAX_DAYS = int(os.environ.get("MAX_DAYS", "30"))
RECONCILE_SECONDS = int(os.environ.get("RECONCILE_SECONDS", "60"))
PORT = int(os.environ.get("PORT", "8080"))

SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
KUBE_URL = "https://kubernetes.default.svc"
INGRESS_PATH = f"/apis/networking.k8s.io/v1/namespaces/{NAMESPACE}/ingresses/{FUNNEL_INGRESS}"
CONFIGMAPS_PATH = f"/api/v1/namespaces/{NAMESPACE}/configmaps"
FUNNEL_ANNOTATION = "tailscale.com/funnel"

# Serialises create, revoke and the expiry loop so they never race on the
# state ConfigMap, the funnel annotation or an Immich link.
lock = threading.Lock()


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(f"{status}: {message}")
        self.status = status


def request(url, method, headers, body=None, context=None, content_type="application/json"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    if data is not None:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=15, context=context) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, e.read().decode(errors="replace")[:300]) from None
    return json.loads(raw) if raw else None


def immich(method, path, body=None):
    headers = {"x-api-key": IMMICH_API_KEY, "Accept": "application/json"}
    return request(IMMICH_URL + "/api" + path, method, headers, body)


def kube(method, path, body=None, content_type="application/json"):
    # Read the token on every call: the kubelet rotates it.
    with open(f"{SA_DIR}/token") as f:
        headers = {"Authorization": "Bearer " + f.read().strip()}
    context = ssl.create_default_context(cafile=f"{SA_DIR}/ca.crt")
    return request(KUBE_URL + path, method, headers, body, context, content_type)


def now():
    return dt.datetime.now(dt.timezone.utc)


def parse_time(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state():
    """Return (configmap, shares). Each share is stored as one JSON data key."""
    try:
        cm = kube("GET", f"{CONFIGMAPS_PATH}/{STATE_CONFIGMAP}")
    except ApiError as e:
        if e.status != 404:
            raise
        cm = kube("POST", CONFIGMAPS_PATH, {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            # Not in git and without Argo CD's tracking label, so Argo CD
            # neither prunes nor resets it.
            "metadata": {"name": STATE_CONFIGMAP, "labels": {"app.kubernetes.io/managed-by": "immich-share"}},
            "data": {},
        })
    shares = []
    for share_id, raw in (cm.get("data") or {}).items():
        share = json.loads(raw)
        share["id"] = share_id
        share["expires_at"] = parse_time(share["expires_at"])
        shares.append(share)
    return cm, sorted(shares, key=lambda s: s["expires_at"])


def save_state(cm, shares):
    cm["data"] = {
        s["id"]: json.dumps({
            "name": s["name"],
            "album": s["album"],
            "link_id": s["link_id"],
            "expires_at": iso(s["expires_at"]),
        })
        for s in shares
    }
    # The PUT carries the resourceVersion we read, so a concurrent edit fails
    # with 409 instead of being overwritten.
    kube("PUT", f"{CONFIGMAPS_PATH}/{STATE_CONFIGMAP}", cm)


def funnel_status():
    """Return (funnel on, public hostname or None)."""
    ing = kube("GET", INGRESS_PATH)
    on = ing["metadata"].get("annotations", {}).get(FUNNEL_ANNOTATION) == "true"
    lb = ing.get("status", {}).get("loadBalancer", {}).get("ingress") or [{}]
    # The operator fills this in with the device's MagicDNS name.
    return on, lb[0].get("hostname")


def set_funnel(on):
    if funnel_status()[0] == on:
        return
    patch = {"metadata": {"annotations": {FUNNEL_ANNOTATION: "true" if on else None}}}
    kube("PATCH", INGRESS_PATH, patch, "application/merge-patch+json")
    print(f"funnel {'on' if on else 'off'}", flush=True)


def delete_link(share):
    try:
        immich("DELETE", "/shared-links/" + share["link_id"])
    except ApiError as e:
        if e.status != 404:
            raise
    print(f"removed share {share['id']} ({share['name']})", flush=True)


def reconcile():
    with lock:
        cm, shares = load_state()
        link_ids = {link["id"] for link in immich("GET", "/shared-links")}
        keep = []
        for share in shares:
            if share["expires_at"] <= now() or share["link_id"] not in link_ids:
                # Expired, or the link was deleted in Immich itself.
                try:
                    delete_link(share)
                except ApiError as e:
                    # Keep the record so the next pass retries; Immich still
                    # refuses the link after its own expiresAt.
                    print(f"could not delete Immich link for {share['id']}: {e}", flush=True)
                    keep.append(share)
                    continue
            else:
                keep.append(share)
        if len(keep) != len(shares):
            save_state(cm, keep)
        set_funnel(any(s["expires_at"] > now() for s in keep))


def reconcile_loop():
    while True:
        try:
            reconcile()
        except Exception as e:  # keep the loop alive through API outages
            print(f"reconcile failed: {e}", flush=True)
        time.sleep(RECONCILE_SECONDS)


def create_share(form):
    name = form.get("name", "").strip()
    album_id = form.get("album", "")
    password = form.get("password", "")
    allow_download = form.get("allow_download") == "on"
    if not 1 <= len(name) <= 60:
        raise ValueError("Give the share a name of 1 to 60 characters.")
    try:
        expires_at = parse_time(form.get("expires_at", ""))
    except ValueError:
        raise ValueError("Pick an expiry date.") from None
    if expires_at.tzinfo is None:
        raise ValueError("The expiry date is missing its time zone.")
    if expires_at < now() + dt.timedelta(minutes=5):
        raise ValueError("The expiry must be at least 5 minutes from now.")
    if expires_at > now() + dt.timedelta(days=MAX_DAYS):
        raise ValueError(f"The expiry can be at most {MAX_DAYS} days from now.")
    albums = {a["id"]: a["albumName"] for a in immich("GET", "/albums")}
    if album_id not in albums:
        raise ValueError("Pick an album.")

    body = {
        "type": "ALBUM",
        "albumId": album_id,
        "description": name,
        "expiresAt": iso(expires_at),
        "allowDownload": allow_download,
        "allowUpload": False,
        "showMetadata": False,
    }
    if password:
        body["password"] = password

    with lock:
        cm, shares = load_state()
        link = immich("POST", "/shared-links", body)
        shares.append({
            "id": secrets.token_hex(4),
            "name": name,
            "album": albums[album_id],
            "link_id": link["id"],
            "expires_at": expires_at,
        })
        try:
            save_state(cm, shares)
        except Exception:
            immich("DELETE", "/shared-links/" + link["id"])
            raise
        set_funnel(True)


def revoke_share(share_id):
    with lock:
        cm, shares = load_state()
        share = next((s for s in shares if s["id"] == share_id), None)
        if share is None:
            raise ValueError("That share no longer exists.")
        delete_link(share)
        rest = [s for s in shares if s["id"] != share_id]
        save_state(cm, rest)
        set_funnel(bool(rest))


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{refresh}
<title>Immich sharing</title>
<style>
  :root {{ color-scheme: light dark; --muted: #6b7280; --line: #d1d5db; --accent: #2563eb; --bad: #b91c1c; }}
  body {{ font: 15px/1.5 system-ui, sans-serif; max-width: 860px; margin: 0 auto; padding: 24px 16px; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; }}
  h2 {{ font-size: 1.1rem; margin: 32px 0 8px; }}
  p.lead, .muted {{ color: var(--muted); }}
  form.create {{ display: grid; gap: 12px; padding: 16px; border: 1px solid var(--line); border-radius: 8px; }}
  label {{ display: grid; gap: 4px; font-weight: 600; }}
  label.check {{ display: flex; gap: 8px; align-items: center; font-weight: 400; }}
  input, select, button {{ font: inherit; padding: 6px 8px; }}
  .presets {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .presets button {{ padding: 2px 10px; }}
  button.primary {{ background: var(--accent); color: white; border: 0; border-radius: 6px; padding: 8px 14px; justify-self: start; }}
  .error {{ color: var(--bad); font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); vertical-align: top; }}
  td.url {{ word-break: break-all; }}
  td form {{ margin: 0; }}
</style>
</head>
<body>
<h1>Immich sharing</h1>
<p class="lead">Shares are served from {funnel_host}. That address is public only while at
least one share is active. Each share's link stops working at its own expiry.</p>
<p class="muted">Funnel is {funnel_state}.</p>
{error}
<form class="create" method="post" action="/shares">
  <label>Name <input name="name" maxlength="60" required placeholder="Grandma's visit"></label>
  <label>Album <select name="album" required>{album_options}</select></label>
  <label>Expires
    <input type="datetime-local" id="expires" required>
    <span class="presets">
      <button type="button" data-hours="24">1 day</button>
      <button type="button" data-hours="48">48 hours</button>
      <button type="button" data-hours="168">7 days</button>
      <button type="button" data-hours="720">30 days</button>
    </span>
  </label>
  <input type="hidden" name="expires_at" id="expires_at">
  <label>Password (optional) <input name="password" type="text" autocomplete="off"></label>
  <label class="check"><input type="checkbox" name="allow_download"> Allow downloads</label>
  <button class="primary" type="submit">Create share</button>
</form>

<h2>Active shares</h2>
{shares}

<script>
  var input = document.getElementById('expires');
  function setHours(h) {{
    var d = new Date(Date.now() + h * 3600 * 1000);
    d.setSeconds(0, 0);
    input.value = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  }}
  setHours(168);
  document.querySelectorAll('.presets button').forEach(function (b) {{
    b.addEventListener('click', function () {{ setHours(Number(b.dataset.hours)); }});
  }});
  document.querySelector('form.create').addEventListener('submit', function () {{
    // datetime-local is the browser's local time; send UTC.
    document.getElementById('expires_at').value = new Date(input.value).toISOString();
  }});
  document.querySelectorAll('time').forEach(function (t) {{
    t.textContent = new Date(t.getAttribute('datetime')).toLocaleString();
  }});
</script>
</body>
</html>
"""


def render_page(error=None):
    e = html.escape
    albums = sorted(immich("GET", "/albums"), key=lambda a: a["albumName"].lower())
    album_options = '<option value="">Choose an album</option>' + "".join(
        f'<option value="{e(a["id"])}">{e(a["albumName"])} ({a["assetCount"]})</option>' for a in albums
    )
    keys = {link["id"]: link["key"] for link in immich("GET", "/shared-links")}
    _, shares = load_state()
    funnel_on, host = funnel_status()
    pending = bool(shares) and not (funnel_on and host)
    if shares:
        rows = []
        for s in shares:
            key = keys.get(s["link_id"])
            if host and key:
                url = f"https://{host}/share/{key}"
                link = f'<a href="{e(url)}">{e(url)}</a>'
            else:
                link = '<span class="muted">Waiting for the funnel…</span>'
            rows.append(
                f"<tr><td>{e(s['name'])}<br><span class='muted'>{e(s['album'])}</span></td>"
                f"<td class='url'>{link}</td>"
                f"<td><time datetime='{iso(s['expires_at'])}'>{iso(s['expires_at'])}</time></td>"
                f"<td><form method='post' action='/shares/{e(s['id'])}/revoke'>"
                f"<button type='submit'>Revoke now</button></form></td></tr>"
            )
        share_html = (
            "<table><thead><tr><th>Share</th><th>Link</th><th>Expires</th><th></th></tr></thead>"
            "<tbody>" + "".join(rows) + "</tbody></table>"
        )
    else:
        share_html = '<p class="muted">No active shares.</p>'
    return PAGE.format(
        refresh='<meta http-equiv="refresh" content="10">' if pending and not error else "",
        funnel_host=e(host or "the share funnel"),
        funnel_state="on" if funnel_on else "off",
        error=f'<p class="error">{e(error)}</p>' if error else "",
        album_options=album_options,
        shares=share_html,
    )


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type="text/html; charset=utf-8"):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def redirect_home(self):
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/healthz":
            self.send(200, "ok", "text/plain")
        elif self.path == "/":
            try:
                self.send(200, render_page())
            except Exception as e:
                self.send(502, f"Could not reach Immich or Kubernetes: {html.escape(str(e))}")
        else:
            self.send(404, "not found", "text/plain")

    def do_POST(self):
        # Authelia's lax session cookie already stops cross-site POSTs; this
        # is a second check that the form came from this page.
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlparse(origin).netloc != self.headers.get("Host"):
            self.send(403, "cross-origin request refused", "text/plain")
            return
        length = int(self.headers.get("Content-Length") or 0)
        form = dict(urllib.parse.parse_qsl(self.rfile.read(length).decode()))
        revoke = re.fullmatch(r"/shares/([0-9a-f]+)/revoke", self.path)
        try:
            if self.path == "/shares":
                create_share(form)
            elif revoke:
                revoke_share(revoke.group(1))
            else:
                self.send(404, "not found", "text/plain")
                return
        except (ValueError, ApiError) as e:
            try:
                self.send(400, render_page(error=str(e)))
            except Exception:
                self.send(400, str(e), "text/plain")
            return
        self.redirect_home()

    def log_message(self, fmt, *args):
        if not self.path.startswith("/healthz"):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    threading.Thread(target=reconcile_loop, daemon=True).start()
    print(f"listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
