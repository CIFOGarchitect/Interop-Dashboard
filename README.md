# Utah Interoperability Dashboard — Production Shell

System-status dashboard for Utah responders, designed to scale to FEMA
Region 8. Audience: **restricted** — dispatch centers, regional LNOs,
fire, EMS, police.

## Current state: PRODUCTION SHELL — NO FABRICATED DATA

Status and activity return empty lists with `connected: false` until a
real source plugs in. There are no simulated talkgroups, sites, or
statuses anywhere in this version. The only real data is the
Broadcastify audio feed list (verified public listings) and the region
definitions (public geography). The "Request interop support" steps are
placeholders marked TBD — not doctrine, no real phone numbers.

This folder replaces the v2 demo folder as the version to deploy. The
older files remain for reference:

- `utah-interop-dashboard-demo.html` — v1 standalone demo (simulated)
- `utah-interop-dashboard/` — v2 server edition (simulated)

## Run locally

```bash
DASHBOARD_USERNAME=<you-choose> DASHBOARD_PASSWORD=<you-choose> \
  python3 utah-interop-server.py
# open http://localhost:8892/ — the browser will prompt for the login
```

## Access gate: shared password (interim, Oct 30, 2026)

Every request requires HTTP Basic Auth. Set the credentials ONLY as
environment variables on the host (Render: Environment tab):
`DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD`. Never put them in the
repo, in `render.yaml`, or in chat. If they are unset, the server
rejects every request (fail closed). This is a shared credential: it
cannot identify individual users, and it must be changed if it leaks or
a holder leaves. Cloudflare Access (per-user login) remains the
longer-term replacement, parked until a domain is available in
Cloudflare.

## Endpoints

- `/` — dashboard page
- `/api/status` — system health (empty until a source connects)
- `/api/activity` — talkgroup activity (empty until a source connects)
- `/api/feeds` — Broadcastify Utah audio feed names + listen-page link

## Before any deployment: ACCESS CONTROL (required)

The shared-password gate above must be active before the URL is shared
with anyone. Do not deploy this shell publicly without it.

## Broadcastify Calls wiring (Oct 30, 2026 — key approved)

`/api/activity` fetches live call metadata for the UCA P25 system
(RadioReference sid 12042) and shows talkgroup + service + last-heard
only. Audio URLs and source/unit IDs are stripped server-side and
never reach the page. One server-side fetch per 60 seconds serves all
viewers. Auth: the server mints its own short-lived JWT per portal
docs (HS256, Key ID + App ID, 1-hour expiry) — no Broadcastify user
login needed. Environment variables (Render: Environment tab, never
the repo, never chat):

- `BROADCASTIFY_API_KEY` — Calls API key (JWT HMAC secret)
- `BROADCASTIFY_API_KEY_ID` — Key ID, from API Key definitions
- `BROADCASTIFY_APP_ID` — Application ID, from application definitions
- `BROADCASTIFY_SYSTEM_ID` — optional, defaults to `12042`
- `BROADCASTIFY_CALLS_ENDPOINT` — `https://api.bcfy.io/calls/v1/live/`
  (live method from the portal Calls docs; use `{sid}` in the URL
  where the system id belongs, if the method needs it)

If the API answers but returns no UCA groups, a Utah node is not
feeding UCA — that is a coverage gap, not a code bug. If the live
method takes filter parameters (system/group), add them to the
endpoint URL so reads — and metered cost — stay scoped to UCA.

## Going live (in order)

1. **Broadcastify Calls Client API.** See above — wiring is in place,
   pending the endpoint detail from the portal docs.
2. **Broadcastify Live Audio Feed Catalog API.** Replace the static
   feed list with programmatic county-by-county listings.
3. **UCA official feed.** Authoritative system activity/status, if
   provided — the long-term source.
4. **Fleet data.** Only add real talkgroup/site data once its handling
   marking is confirmed and agency-restricted entries are excluded as
   required.

## Deploy (later, same route as the alerts board)

Render web service, Python, no build command, start command
`python3 utah-interop-server.py`. The server reads `PORT` from the
environment. Keep all files at the repo root, or prefix the start
command with the folder name.
