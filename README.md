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
- `BROADCASTIFY_SYSTEM_ID` — optional, defaults to `12042` (UCA P25);
  change it to limit the dashboard to a different system instead
- `BROADCASTIFY_TALKGROUPS` — optional allowlist: comma-separated
  decimal talkgroup IDs (the part after `12042-` in a group ID).
  When set, only those talkgroups reach the page; when unset, all
  talkgroups on the system pass. Keep the list in Render only —
  never in the repo or in chat.
- `BROADCASTIFY_CALLS_ENDPOINT` — `https://api.bcfy.io/calls/v1/live/`
  (live method from the portal Calls docs). The server scopes the
  fetch itself: if the URL has no query attribute, it appends
  `?sid=<system>` (live parameters are mutually exclusive, so an
  existing `sid`, `groups`, `nodeId`, or `playlist_uuid` is respected).
  With no `pos`/`init`, the live method returns the last 5 minutes
  of calls for that system — well matched to the 60-second poll.
- `BROADCASTIFY_USER_ID` / `BROADCASTIFY_USER_TOKEN` — required for
  live calls except public playlists: the authenticated user token
  (`sub`/`utk` in the JWT) from the common endpoint's auth method.
  How to obtain and refresh these is still to be confirmed from the
  portal Common Endpoint Docs; do not put a Broadcastify account
  password in chat or in the repo.

If the API answers but returns no UCA groups, a Utah node is not
feeding UCA — that is a coverage gap, not a code bug. If the live
method takes filter parameters (system/group), add them to the
endpoint URL so reads — and metered cost — stay scoped to UCA.

## Talkgroup aliases (channel names)

The activity panel shows the channel alias when one is mapped, with
the talkgroup number kept alongside it; unmapped talkgroups still
show their number. Format (header row required):

```
talkgroup,alias,region
1234,EXAMPLE ALPHA,Wasatch Front
5678,EXAMPLE BRAVO,
```

`region` is optional — use a full region name, or leave it blank for
Statewide. A partial list is fine; only listed talkgroups get names.

**How to provide the file — do NOT put it in the repo or in chat.**
The alias list is restricted working material. Recommended route:
Render dashboard → service → Environment → Secret Files → Add
Secret File, filename `talkgroups.csv`, paste the file contents.
The server reads `/etc/secrets/talkgroups.csv` automatically on
restart. Alternative: set `TALKGROUPS_CSV_PATH` to a file path the
server can read. Fallback if the Secret File mount is not working:
set `TALKGROUPS_CSV_CONTENT` to the full CSV text as an environment
variable and restart — the server parses it directly, no file
mount needed. A repo file named `utah-interop-talkgroups.csv`
is also read, but only use that route if the repo is private and
the list is approved for it — never in a public repo.

**Diagnosing alias loading:** `/api/activity` reports
`aliases_loaded` (mapped rows), `alias_source` (`env`, `file`, or
`none`), `alias_path` (file found, if any), and
`alias_secret_files` (CSV filenames visible under `/etc/secrets`,
names only). If `alias_secret_files` is empty, no Secret File is
mounted on this service.

**Field-names diagnostic:** `/api/activity` also reports
`call_fields` (field names present in the raw live records, names
only — never values, audio URLs, or unit IDs) and
`call_records_seen` (raw records in the last fetch). This is a
snapshot of the current 5-minute live window, not a full schema;
rare fields may not appear in a given window.

## Cost control — incremental fetching (pos)

The live method bills per record read. Polling it bare every 60s
re-reads the same 5-minute window about 5 times, billing every
re-read — that is how a low per-key cap is hit in under an hour.
The server therefore fetches incrementally: the first fetch takes
the last 5 minutes, then each later fetch sends `pos` (newest call
timestamp from the last response) and receives only newer calls.
A 5-minute activity state on the server keeps the panel showing
the same last-5-minutes view. After a gap over 5 minutes (restart,
outage, cap), it takes a fresh window instead of a huge backfill,
and a failed fetch leaves state and position untouched.

**Key cap vs account balance are different.** The per-key monthly
spend cap (set on the key in the portal) stops that key even when
the shared prepaid account balance still has funds. If the API
returns HTTP 402 "Key spend cap reached," raise that key's cap in
the portal — and watch a day of incremental-fetch spend before
choosing a monthly cap, rather than removing the cap entirely.

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
