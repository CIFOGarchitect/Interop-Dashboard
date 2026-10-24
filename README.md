# Utah Interoperability Dashboard — v2 (Demo Data)

System-status dashboard for Utah responders, designed to scale to FEMA
Region 8. Audience: **restricted** — dispatch centers, regional LNOs,
fire, EMS, police.

## Current state: DEMO DATA ONLY

All talkgroups, sites, and activity are simulated. No real UCA fleet data
is in this project. Every demo talkgroup is DEMO-prefixed. The
"Request interop support" steps are placeholders marked TBD — they are
not doctrine and contain no real phone numbers.

## Run locally

```bash
python3 utah-interop-server.py
# open http://localhost:8891/
```

## Endpoints

- `/` — dashboard page
- `/api/status` — system health cards + region definitions (demo)
- `/api/activity` — talkgroup activity (simulated)
- `/api/feeds` — Broadcastify Utah audio feed names + listen-page link

## Going live (in order)

1. **Access control first.** Add a login gate or network restriction at
   deployment. Do not deploy this demo publicly as-is.
2. **Broadcastify Calls Client API.** After developer approval, replace
   `simulate_activity()` in the server with live call metadata
   (system, talkgroup, timestamp). Display talkgroup + area + time
   only — no audio, no source/unit IDs. Key goes in an environment
   variable, never in the repo. Verify a Utah node covers UCA first.
3. **Broadcastify Live Audio Feed Catalog API.** Replace the static
   feed list with programmatic county-by-county listings.
4. **UCA official feed.** Authoritative system activity/status, if
   provided — the long-term source.
5. **Fleet data.** Only add real talkgroup/site data once its handling
   marking is confirmed and agency-restricted entries are excluded as
   required.

## Deploy (later, same route as the alerts board)

Render web service, Python, no build command, start command
`python3 utah-interop-server.py`. The server reads `PORT` from the
environment. Keep all files at the repo root, or prefix the start
command with the folder name.
