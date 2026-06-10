# Subnet 105 — Orchestrator Analytics Dashboard

A self-contained dashboard for analyzing Beam (Bittensor Subnet 105) orchestrators,
built on the public BeamCore dashboard API (`https://data.b1m.ai/api/dashboard/*`).

## Run

```bash
cd dashboard
python3 serve.py            # default port 8765
# open http://localhost:8765
```

`serve.py` (Python stdlib only — no pip installs) serves the page and **proxies the
BeamCore API** so the browser avoids CORS. Each successful fetch also refreshes
`data.json` as an offline snapshot.

### VPS / hosting enrichment (optional, refreshable)

```bash
python3 geo.py             # fetch live orchestrators, resolve gateway IPs, geolocate
python3 geo.py --local     # use bundled data.json instead of fetching
```

`geo.py` reads each orchestrator's `gateway_url`, resolves it to an IP (DNS for
hostnames), and geolocates via **ip-api.com** → provider/ASN, datacenter flag,
country/city — written to `geo.json`, which the dashboard joins by UID. The
orchestrators' gateway IPs are public (already on data.b1m.ai). The 15
"Shared"-gateway orchestrators point at BeamCore's gateway, not their own host,
and are flagged. Re-run `geo.py` to refresh as orchestrators change.

### Traffic tracking (per-orchestrator rate over time)

The API exposes only *cumulative* counts (and `total_bytes_transferred` is 0 — byte
volume isn't published), so traffic is measured in verified **tasks/transfers**, and a
real **rate** requires sampling over time:

```bash
python3 track.py               # one poll → append to traffic.jsonl  (for cron)
python3 track.py --loop 600     # poll every 600s until Ctrl+C
python3 track.py --local        # read data.json instead of fetching live
```

Each poll appends one compact line to `traffic.jsonl`. The dashboard diffs the first
and last samples to show **Δ tasks/hour** (column + drawer) and a lifetime sparkline.
Until two samples ≥2 min apart exist it shows "collecting…". Run it on a schedule:

```cron
*/10 * * * * cd /path/to/dashboard && python3 track.py >> track.log 2>&1
```

> Opening `index.html` directly via `file://` will fall back to the bundled
> `data.json` snapshot, but most browsers block `file://` fetches — use the server.

Custom port: `python3 serve.py 9000`.

## What it shows

- **Overview cards** — slotted/empty UIDs, qualified vs qualifying, penalized count
  (POP vs fraud/sybil), workers, tasks, TAO distributed.
- **Charts** — pool split, PRISM final-score histogram (stacked by pool),
  throughput-vs-reliability scatter (bubble = epoch weight), top-15 by epoch weight.
- **Penalty overview** — every penalized orchestrator, with POP vs **fraud/sybil**
  events broken out (`fraud/sybil = total events − failed POP payments`).
- **Infrastructure** — top hosting providers (own-VPS orchestrators) and
  country/decentralization breakdown, with a datacenter-vs-residential split.
- **Orchestrator table** — sortable/filterable (pool, penalized, ready, connected,
  dedicated/datacenter/residential/shared gateway, country); **Geo + Provider
  columns**; search by uid/hotkey/region/provider/country/IP.
- **Detail drawer** (click any row) — the full PRISM breakdown:
  `performance = throughput×0.4 + reliability×0.6`, then
  `final = performance × readiness × penalty`, plus confidence/graduation,
  penalties, and routing/weight fields.

## Data source & freshness

- Live data is read from `data.b1m.ai` via the proxy; the source badge shows
  **live** vs **snapshot** and the fetch age. Hit **⟳ Refresh** for the latest epoch.
- `data.json` is a committed snapshot fallback so the dashboard works offline.

## Files

| File | Purpose |
|------|---------|
| `index.html` | The dashboard (vanilla JS, no dependencies, hand-rolled SVG charts) |
| `serve.py`   | Static server + BeamCore API proxy (Python stdlib) |
| `geo.py`     | VPS/hosting enrichment — resolves gateway IPs + geolocates → `geo.json` |
| `track.py`   | Traffic poller — appends per-orchestrator volume snapshots → `traffic.jsonl` |
| `data.json`  | Offline snapshot fallback (auto-refreshed by the server) |
| `traffic.jsonl` | Append-only traffic time-series (one line per poll; for tasks/hr + sparkline) |
| `geo.json`   | VPS/hosting data keyed by UID (refresh with `geo.py`) |

## Notes

- The dashboard exposes aggregate penalty counts (total events + POP subset).
  Fraud/sybil is derived as `penalty_event_count − failed_pop_payments`; when that
  is 0 for every orchestrator, no fraud/sybil penalties are active.
- Endpoints proxied: `/api/dashboard/orchestrators`, `/metrics`, `/workers`.
