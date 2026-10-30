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
  source/unit IDs are stripped and never leave the server.
  AUTH (per portal docs, Getting Started): Broadcastify does NOT issue
  tokens — the server mints its own short-lived JWT for every fetch:
  header {alg HS256, typ JWT, kid=<API_KEY_ID>}, payload {iss=<APP_ID>,
  iat=now, exp=now+3600}, signature HMAC-SHA256(api_key, header.payload)
  with base64url encoding and trailing "=" stripped. No Broadcastify
  user login is needed (the /common/v1/auth method only supplies sub/utk
  for user-authenticated endpoints, which this dashboard does not use).
  Secrets/ids go in environment variables only, never the repo:
  BROADCASTIFY_API_KEY (HMAC secret), BROADCASTIFY_API_KEY_ID (kid),
  BROADCASTIFY_APP_ID (iss). The exact live-calls method path under
  https://api.bcfy.io/calls/v1 comes from the portal Calls docs and is
  set via BROADCASTIFY_CALLS_ENDPOINT; until that is set, /api/activity
  honestly reports connected:false. One server-side fetch per 60s serves
  all dashboard viewers (cost does not multiply per viewer). Verify a
  Utah node covers UCA before relying on it: if the API answers but
  returns no UCA groups, coverage — not the code — is the gap.
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
import csv
import hashlib
import hmac
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
#   BROADCASTIFY_API_KEY        Calls API key (HMAC secret for JWT signing)
#   BROADCASTIFY_API_KEY_ID     Key ID (JWT header "kid")
#   BROADCASTIFY_APP_ID         Application ID (JWT payload "iss")
#   BROADCASTIFY_SYSTEM_ID      RadioReference sid; default 12042 (UCA P25)
#   BROADCASTIFY_TALKGROUPS     Optional allowlist: comma-separated
#     decimal talkgroup IDs (the part after "12042-" in groupId), e.g.
#     "1234,5678". When set, only those talkgroups reach the page;
#     when unset, all talkgroups on the system pass. Set it in the
#     host's environment, never in the repo or chat.
#   BROADCASTIFY_CALLS_ENDPOINT Full live-calls method URL from the
#     portal Calls docs (under https://api.bcfy.io/calls/v1). Use {sid}
#     where the system id belongs. Until this is set, /api/activity
#     reports connected:false (no guessing).
def _b64url(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _mint_jwt(api_key, key_id, app_id, now=None, lifetime=3600,
              user_id=None, user_token=None):
    """Mint a short-lived JWT per portal docs (HS256, 1-hour expiry).
    Verified against the docs' worked sample (same inputs, 60s lifetime
    -> same token). Live Calls (non-playlist) requires an authenticated
    user token in the JWT: when user_id/user_token are supplied they
    become payload sub (integer) and utk."""
    now = int(now if now is not None else time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {"iss": app_id, "iat": now, "exp": now + lifetime}
    if user_id is not None and user_token:
        payload["sub"] = int(user_id)
        payload["utk"] = user_token
    enc_header = _b64url(json.dumps(header, separators=(",", ":")).encode())
    enc_payload = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = "%s.%s" % (enc_header, enc_payload)
    sig = hmac.new(api_key.encode(), signing_input.encode(),
                   hashlib.sha256).digest()
    return "%s.%s" % (signing_input, _b64url(sig))
CALLS_TTL_SECONDS = 60
CALLS_MAX_ROWS = 50
_calls_cache = {"fetched_at": 0.0, "activity": [], "connected": False,
                "error": None}
_calls_lock = threading.Lock()


# --- Talkgroup alias CSV (channel names) -------------------------------
# Format: talkgroup,alias,region  (region optional, full region name or
# blank for Statewide). The alias list is restricted working material:
# it must NEVER go in the repo or in chat. Delivery route is the host's
# Secret Files (Render mounts them at /etc/secrets/), or a path set in
# TALKGROUPS_CSV_PATH. A repo file named utah-interop-talkgroups.csv
# next to this server is also read, but only if the repo is private
# and the list is approved for it. Absent file -> numbers only.
_alias_cache = {"path": None, "mtime": None, "size": None, "map": {}}


def _alias_csv_path():
    env_path = os.environ.get("TALKGROUPS_CSV_PATH", "").strip()
    if env_path:
        return env_path
    for candidate in ("/etc/secrets/talkgroups.csv",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "utah-interop-talkgroups.csv")):
        if os.path.exists(candidate):
            return candidate
    return None


def _load_aliases():
    """Load talkgroup -> {alias, region} from CSV, cached by mtime."""
    path = _alias_csv_path()
    if not path or not os.path.exists(path):
        return {}
    try:
        stat = os.stat(path)
    except OSError:
        return {}
    if (_alias_cache["path"] == path
            and _alias_cache["mtime"] == stat.st_mtime
            and _alias_cache["size"] == stat.st_size):
        return _alias_cache["map"]
    mapping = {}
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                tg = (row.get("talkgroup") or "").strip()
                alias = (row.get("alias") or "").strip()
                region = (row.get("region") or "").strip()
                if tg and alias:
                    mapping[tg] = {"alias": alias,
                                   "region": region or None}
    except (OSError, csv.Error):
        return _alias_cache["map"]
    _alias_cache.update(path=path, mtime=stat.st_mtime,
                        size=stat.st_size, map=mapping)
    return mapping


def _calls_to_rows(calls, sid, now, talkgroups=None, aliases=None):
    """Collapse raw call records to one row per talkgroup, metadata only.
    Drops audio URLs, source/unit IDs, node ids, and everything else.
    talkgroups: optional set of allowed decimal talkgroup IDs; when
    given, only those talkgroups pass. aliases: optional mapping from
    _load_aliases(); unmapped talkgroups keep number-only display."""
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
        if not tg or (talkgroups is not None and tg not in talkgroups):
            continue
        if tg in latest and latest[tg] >= ts:
            continue
        latest[tg] = ts
    rows = []
    for tg, ts in sorted(latest.items(), key=lambda kv: kv[1], reverse=True):
        age = max(0.0, now - ts)
        info = (aliases or {}).get(tg, {})
        rows.append({
            "talkgroup": tg,
            "alias": info.get("alias"),
            "service": "UCA P25",
            "region_name": info.get("region") or "Statewide",
            "active_now": age <= 120,
            "last_heard_min": int(age // 60),
        })
    return rows[:CALLS_MAX_ROWS]


def get_calls_activity():
    """Fetch (cached 60s) or return the honest not-connected state."""
    key = os.environ.get("BROADCASTIFY_API_KEY")
    key_id = os.environ.get("BROADCASTIFY_API_KEY_ID")
    app_id = os.environ.get("BROADCASTIFY_APP_ID")
    endpoint = os.environ.get("BROADCASTIFY_CALLS_ENDPOINT")
    sid = os.environ.get("BROADCASTIFY_SYSTEM_ID", "12042")
    tg_env = os.environ.get("BROADCASTIFY_TALKGROUPS", "").strip()
    talkgroups = ({t.strip() for t in tg_env.split(",") if t.strip()}
                  if tg_env else None)
    if not key or not key_id or not app_id or not endpoint:
        return {"connected": False, "source": "Broadcastify Calls",
                "activity": [],
                "error": "Calls API not configured (key/key id/app id/endpoint missing)"}
    now = time.time()
    with _calls_lock:
        if now - _calls_cache["fetched_at"] < CALLS_TTL_SECONDS:
            cached = dict(_calls_cache)
            cached.pop("fetched_at", None)
            return cached
    # Live Calls parameters are mutually exclusive (playlist_uuid, sid,
    # nodeId, groups). If the endpoint has no query attribute at all,
    # scope the fetch to this system with ?sid=<sid> so the request
    # names an entity and the pull itself is system-only, not global.
    url = endpoint.replace("{sid}", sid)
    parts = urllib.parse.urlparse(url)
    query = dict(urllib.parse.parse_qsl(parts.query))
    if not any(k in query for k in ("playlist_uuid", "sid", "nodeId",
                                    "groups")):
        query["sid"] = sid
        url = urllib.parse.urlunparse(
            parts._replace(query=urllib.parse.urlencode(query)))
    token = _mint_jwt(key, key_id, app_id, now=now,
                      user_id=os.environ.get("BROADCASTIFY_USER_ID"),
                      user_token=os.environ.get("BROADCASTIFY_USER_TOKEN"))
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer %s" % token,
                      "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network/auth/parse failure: fail soft, no crash
        # Surface the HTTP status (and any short error body Broadcastify
        # returns) so a rejection can be diagnosed without guessing:
        # 401 = JWT rejected, 403 = entitlement/forbidden, 404 = path
        # wrong, 400 = missing/invalid parameter.
        detail = type(exc).__name__
        if isinstance(exc, urllib.error.HTTPError):
            detail = "HTTP %s" % exc.code
            try:
                body = exc.read().decode("utf-8", "replace").strip()
                if body:
                    detail += " " + body[:200]
            except Exception:
                pass
        result = {"connected": False, "source": "Broadcastify Calls",
                  "activity": [], "error": "Calls fetch failed: %s" % detail}
        with _calls_lock:
            _calls_cache.update(result, fetched_at=now)
        return result
    if isinstance(data, dict):
        calls = data.get("calls") or data.get("results") or data.get("data") or []
    elif isinstance(data, list):
        calls = data
    else:
        calls = []
    rows = _calls_to_rows(calls, sid, now, talkgroups, _load_aliases())
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
