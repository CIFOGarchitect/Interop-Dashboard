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

TO CONNECT A LIVE SOURCE (do only when approved):
  1. Broadcastify Calls Client API (bcfy.io/dev) — implement a fetch of
     live call metadata (groupId {sid}-{talkgroup}, ts) for the activity
     endpoint. Display talkgroup + area + time ONLY. Never include audio,
     and never include source/unit IDs in API output. The developer key
     goes in an environment variable, never in the repo. Verify a Utah
     node covers UCA before relying on it.
  2. Broadcastify Live Audio Feed Catalog API — replace the static FEEDS
     list with programmatic county-by-county listings.
  3. UCA official feed — authoritative system activity/status, if
     provided. This is the long-term source.

ACCESS CONTROL: REQUIRED BEFORE ANY DEPLOYMENT. This dashboard is for a
RESTRICTED audience (dispatch centers, regional LNOs, fire/EMS/law).
Add a login gate or network restriction before anyone uses it. Do not
deploy this shell publicly or without an access gate.

Stdlib only. Reads PORT from the environment (Render assigns one).
Default local port 8892.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

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
            # No live source connected yet: empty systems, honest flag.
            send_json(self, {"connected": False, "source": None,
                             "regions": REGIONS, "systems": []})
        elif path == "/api/activity":
            # No live source connected yet: empty activity, honest flag.
            send_json(self, {"connected": False, "source": None, "activity": []})
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
