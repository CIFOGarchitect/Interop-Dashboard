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
python3 utah-interop-server.py
# open http://localhost:8892/
```

## Endpoints

- `/` — dashboard page
- `/api/status` — system health (empty until a source connects)
- `/api/activity` — talkgroup activity (empty until a source connects)
- `/api/feeds` — Broadcastify Utah audio feed names + listen-page link

## Before any deployment: ACCESS CONTROL (required)

Add a login gate or network restriction. Do not deploy this shell
publicly or without an access gate.

## Going live (in order)

1. **Broadcastify Calls Client API.** After developer approval,
   implement the activity fetch in the server: live call metadata
   (system, talkgroup, timestamp). Display talkgroup + area + time
   only — no audio, no source/unit IDs. Key in an environment
   variable, never in the repo. Verify a Utah node covers UCA first.
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
