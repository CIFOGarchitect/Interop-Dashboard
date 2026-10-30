#!/usr/bin/env python3
"""Utah Interoperability Dashboard — PRODUCTION SHELL.

Serves the dashboard page plus JSON APIs:
  /               -> dashboard HTML
  /api/status     -> system health (EMPTY until a live source connects)
  /api/activity   -> talkgroup activity (EMPTY until a live source connects)
  /api/feeds      -> Broadcastify Utah audio feed list (real public listings)

NO FABRICATED DATA. This shell contains no simulated talkgroups, sites,
or statuses. Status and activity return empty lists with connected:false
until a real source is plugged in. Region names are public geography.

BROADCASTIFY CALLS WIRING (added Oct 30, 2026; key approved, see README).
  /api/activity fetches live call metadata for the UCA P25 system
  (RadioReference sid 12042; the older sid 601 system is deprecated)
  and returns talkgroup + service + last-heard ONLY. Audio URLs and
  source/unit IDs are stripped and never leave the server. The developer
  key goes in BROADCASTIFY_API_KEY (environment only, never the repo).
  The exact live-calls endpoint path and auth style come from the
  developer portal docs (bcfy.io/dev/docs, login-gated) and are set via
  BROADCASTIFY_CALLS_ENDPOINT; until that is set, /api/activity honestly
  reports connected:false. One server-side fetch per 60s serves all
  dashboard viewers (cost does not multiply per viewer). Verify a Utah
  node covers UCA before relying on it: if the API answers but returns
  no UCA groups, coverage — not the code — is the gap.
  2. Broadcastify Live Audio Feed Catalog API — replace the static FEEDS
     list with programmatic county-by-county listings.
  3. UCA official feed — authoritative system activity/status, if
     provided. This is the long-term source.

ACCESS CONTROL: SHARED-PASSWORD GATE (interim, chosen Oct 30, 2026).
This dashboard is for a RESTRICTED audience (dispatch centers, regional
LNOs, fire/EMS/law). Every request must pass HTTP Basic Auth against
credentials set ONLY as environment variables on the host (Render):
DASHBOARD_USERNAME and DASHBOARD_PASSWORD. Never commit credentials to
the repo, render.yaml, or chat. If the variables are unset, all requests
are rejected (fail closed). This is a shared credential: it cannot tell
users apart and must be rotated if it leaks or a holder leaves. The
longer-term option (Cloudflare Access, per-user login) is parked until
a domain is available in Cloudflare; it replaces this gate, it does not
stack on top of it unless deliberately configured to do so.

Stdlib only. Reads PORT from the environment (Render assigns one).
Default local port 8892.
"""

import base64
import binascii
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


def check_auth(handler):
    """Shared-password gate. Credentials come only from environment
    variables. Returns True when the request is authorized."""
    username = os.environ.get("DASHBOARD_USERNAME")
    password = os.environ.get("DASHBOARD_PASSWORD")
    if not username or not password:
        return False  # fail closed: no credentials configured, no access
    auth = handler.headers.get("Authorization")
    if not auth or not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    if ":" not in decoded:
        return False
    given_user, given_pass = decoded.split(":", 1)
    return (secrets.compare_digest(given_user, username)
            and secrets.compare_digest(given_pass, password))


def send_unauthorized(handler):
    handler.send_response(401)
    handler.send_header("WWW-Authenticate",
                        'Basic realm="Utah Interop Dashboard"')
    handler.send_header("Content-Type", "text/plain")
    handler.end_headers()
    handler.wfile.write(b"Authentication required.")

PAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "utah-interop-dashboard.html")

# Public geography: Utah's 8 regions and their counties.
REGIONS = {
    "BR": {"name": "Bear River", "counties": "Box Elder, Cache, Rich"},
    "WF": {"name": "Wasatch Front", "counties": "Weber, Davis, Morgan"},
    "OQ": {"name": "Oquirrh", "counties": "Tooele, Salt Lake"},
    "MT": {"name": "Mountain", "counties": "Summit, Wasatch, Utah, Juab"},
    "NE": {"name": "Northeast", "counties": "Daggett, Duchesne, Uintah"},
    "CN": {"name": "Central", "counties": "Millard, Sanpete, Sevier, Piute, Wayne"},
    "SW": {"name": "Southwest", "counties": "Beaver, Iron, Washington, Garfield, Kane"},
    "SE": {"name": "Southeast", "counties": "Carbon, Emery, Grand, San Juan"},
}

# Broadcastify Utah audio feeds — names verified from the public Utah listen
# page on 2026-10-24. These are real public listings, not simulated data.
# Individual feed URLs are not hardcoded (they were not verified); the page
# link below is the verified entry point. Replace with the Live Audio Feed
# Catalog API for programmatic listings later.
FEEDS = {
    "page_url": "https://www.broadcastify.com/listen/stid/49",
    "page_label": "All Utah feeds on Broadcastify",
    "feeds": [
        "Davis County UCA 700 MHz P25 System",
        "Cache County Public Safety",
        "Box Elder and Weber County Public Safety",
        "Utah County Public Safety",
        "Salt Lake County Public Safety",
        "Tooele County Public Safety",
    ],
    "note": "Volunteer-run feeds; coverage varies by county. Audio only — feeds do "
            "not provide machine-readable talkgroup activity.",
}


# --- Broadcastify Calls activity fetch (metadata only) -------------------
# Env vars (set on the host, never in the repo):
#   BROADCASTIFY_API_KEY       Calls Client API developer key
#   BROADCASTIFY_SYSTEM_ID     RadioReference sid; default 12042 (UCA P25)
#   BROADCASTIFY_CALLS_ENDPOINT Full live-calls endpoint URL from the
#     developer portal docs. Use {sid} where the system id belongs and
#     {key} where the key belongs if the documented style needs it in
#     the URL; otherwise the key is sent as a Bearer header. Until this
#     is set, /api/activity reports connected:false (no guessing).
CALLS_TTL_SECONDS = 60
CALLS_MAX_ROWS = 50
_calls_cache = {"fetched_at": 0.0, "activity": [], "connected": False,
                "error": None}
_calls_lock = threading.Lock()


def _calls_to_rows(calls, sid, now):
    """Collapse raw call records to one row per talkgroup, metadata only.
    Drops audio URLs, source/unit IDs, node ids, and everything else."""
    latest = {}
    for item in calls:
        if not isinstance(item, dict):
            continue
        group_id = item.get("groupId") or item.get("group_id") or ""
        ts = item.get("ts")
        if ts is None:
            ts = item.get("timestamp") or item.get("start_time")
        if not group_id or ts is None:
            continue
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            continue
        if ts > 1e12:  # milliseconds -> seconds
            ts /= 1000.0
        prefix = "%s-" % sid
        if not str(group_id).startswith(prefix):
            continue
        tg = str(group_id)[len(prefix):]
        if not tg or (tg in latest and latest[tg] >= ts):
            continue
        latest[tg] = ts
    rows = []
    for tg, ts in sorted(latest.items(), key=lambda kv: kv[1], reverse=True):
        age = max(0.0, now - ts)
        rows.append({
            "talkgroup": tg,
            "service": "UCA P25",
            "region_name": "Statewide",
            "active_now": age <= 120,
            "last_heard_min": int(age // 60),
        })
    return rows[:CALLS_MAX_ROWS]


def get_calls_activity():
    """Fetch (cached 60s) or return the honest not-connected state."""
    key = os.environ.get("BROADCASTIFY_API_KEY")
    endpoint = os.environ.get("BROADCASTIFY_CALLS_ENDPOINT")
    sid = os.environ.get("BROADCASTIFY_SYSTEM_ID", "12042")
    if not key or not endpoint:
        return {"connected": False, "source": "Broadcastify Calls",
                "activity": [],
                "error": "Calls API not configured (key/endpoint missing)"}
    now = time.time()
    with _calls_lock:
        if now - _calls_cache["fetched_at"] < CALLS_TTL_SECONDS:
            cached = dict(_calls_cache)
            cached.pop("fetched_at", None)
            return cached
    url = endpoint.replace("{sid}", sid)
    if "{key}" in url:
        url = url.replace("{key}", urllib.parse.quote(key))
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer %s" % key,
                      "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network/auth/parse failure: fail soft, no crash
        result = {"connected": False, "source": "Broadcastify Calls",
                  "activity": [], "error": "Calls fetch failed: %s" % type(exc).__name__}
        with _calls_lock:
            _calls_cache.update(result, fetched_at=now)
        return result
    if isinstance(data, dict):
        calls = data.get("calls") or data.get("results") or data.get("data") or []
    elif isinstance(data, list):
        calls = data
    else:
        calls = []
    rows = _calls_to_rows(calls, sid, now)
    result = {"connected": True, "source": "Broadcastify Calls",
              "activity": rows, "error": None}
    with _calls_lock:
        _calls_cache.update(result, fetched_at=now)
    return result


def send_json(handler, obj):
    body = json.dumps(obj).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if not check_auth(self):
            send_unauthorized(self)
            return
        path = urlparse(self.path).path
        if path == "/":
            try:
                with open(PAGE_FILE, "rb") as f:
                    body = f.read()
            except OSError:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Dashboard page file missing.")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/status":
            # No live source connected yet: empty systems, honest flag.
            send_json(self, {"connected": False, "source": None,
                             "regions": REGIONS, "systems": []})
        elif path == "/api/activity":
            send_json(self, get_calls_activity())
        elif path == "/api/feeds":
            send_json(self, FEEDS)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8892"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Utah interop dashboard (PRODUCTION SHELL) on port {port}", flush=True)
    server.serve_forever()
