#!/usr/bin/env python3
"""Utah Interoperability Dashboard — v2 server (DEMO DATA).

Serves the dashboard page plus JSON APIs:
  /               -> dashboard HTML
  /api/status     -> system health cards (demo data)
  /api/activity   -> talkgroup activity (SIMULATED data)
  /api/feeds      -> Broadcastify Utah audio feed list (verified names + page link)

DATA STATUS — READ BEFORE USING:
  All talkgroup names, site names, and activity in this version are SIMULATED.
  No real UCA fleet data is in this server. Every demo talkgroup is DEMO-prefixed.

FUTURE DATA PLUG-IN POINTS (do not enable until approved):
  1. Broadcastify Calls Client API (bcfy.io/dev) — replace simulate_activity()
     with a fetch of live call metadata (groupId {sid}-{talkgroup}, ts).
     Display talkgroup + area + time ONLY. Never include audio, and never
     include source/unit IDs in API output. Requires an approved developer
     key, stored as an environment variable (never in the repo).
  2. Broadcastify Live Audio Feed Catalog API — replace the static FEEDS list
     with a programmatic county-by-county feed listing.
  3. UCA official feed — authoritative system activity/status, if provided.

ACCESS CONTROL: not implemented in this version. The dashboard is intended
for a RESTRICTED audience (dispatch centers, regional LNOs, fire/EMS/law).
Add an access gate (login or network restriction) at deployment time; do
not deploy this demo publicly as-is.

Stdlib only. Reads PORT from the environment (Render assigns one).
"""

import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "utah-interop-dashboard.html")

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

# Demo system health — generic demo names only, no real sites.
STATUS = [
    {"region": "BR", "title": "DEMO P25 Site — Bear River", "status": "ok", "label": "Operational",
     "note": "Demo site. No real site data."},
    {"region": "WF", "title": "DEMO VHF Repeater — Wasatch Front", "status": "degraded", "label": "Degraded",
     "note": "Demo status: reduced coverage."},
    {"region": "OQ", "title": "DEMO Gateway — Oquirrh", "status": "ok", "label": "Operational",
     "note": "Demo bridge resource."},
    {"region": "MT", "title": "DEMO P25 Site — Mountain", "status": "out", "label": "Out of service",
     "note": "Demo outage for illustration."},
    {"region": "CN", "title": "DEMO Cache Radio Pool — Central", "status": "ok", "label": "Available",
     "note": "Demo pool: 12 units (fake)."},
    {"region": "SW", "title": "DEMO VHF Repeater — Southwest", "status": "ok", "label": "Operational",
     "note": "Demo site. No real site data."},
    {"region": "NE", "title": "DEMO Gateway — Northeast", "status": "degraded", "label": "Degraded",
     "note": "Demo status: intermittent link."},
    {"region": "SE", "title": "DEMO P25 Site — Southeast", "status": "ok", "label": "Operational",
     "note": "Demo site. No real site data."},
]

# Demo talkgroups — DEMO-prefixed only. Never add real talkgroup names here.
DEMO_TGS = [
    ("DEMO FIRE TAC 1", "Fire"), ("DEMO EMS DISP", "EMS"),
    ("DEMO LAW TAC 2", "Law"), ("DEMO INTEROP CALL", "Interop"),
    ("DEMO FIRE OPS 3", "Fire"), ("DEMO SAR 1", "SAR"),
    ("DEMO EMS TAC 1", "EMS"), ("DEMO LAW DISP", "Law"),
]

# Broadcastify Utah audio feeds — names verified from the public Utah listen
# page on 2026-10-24. Individual feed URLs are not hardcoded (they were not
# verified); the page link below is the verified entry point. Replace with
# the Live Audio Feed Catalog API for programmatic listings later.
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


def simulate_activity(count=8):
    """SIMULATED activity. PLUG-IN POINT: replace with Broadcastify Calls
    Client API live-call metadata when an approved key exists. Keep output
    to talkgroup + service + region + last-heard minutes. Never add source
    (unit) IDs or audio to this output."""
    now = int(time.time())
    rows = []
    for tg, svc in random.sample(DEMO_TGS, min(count, len(DEMO_TGS))):
        region = random.choice(list(REGIONS.keys()))
        mins = random.randint(0, 14)
        rows.append({
            "talkgroup": tg, "service": svc, "region": region,
            "region_name": REGIONS[region]["name"],
            "last_heard_min": mins,
            "active_now": mins == 0,
        })
    rows.sort(key=lambda r: r["last_heard_min"])
    return {"simulated": True, "updated": now, "activity": rows}


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
            send_json(self, {"simulated": True, "regions": REGIONS, "systems": STATUS})
        elif path == "/api/activity":
            send_json(self, simulate_activity())
        elif path == "/api/feeds":
            send_json(self, FEEDS)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8891"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Utah interop dashboard (DEMO DATA) on port {port}", flush=True)
    server.serve_forever()
