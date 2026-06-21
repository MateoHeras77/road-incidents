# Road Incidents — Canadian Highway Network (Middle Mile)

Consolidates road closures, accidents, construction, restrictions, winter road
conditions and traffic cameras from Canada's provincial 511 / road sites into a
single map + list dashboard for Purolator Middle Mile planners. Data is filtered
to **highways** (local streets excluded) and prioritized by proximity to
Purolator facilities.

```
Provincial APIs ──> Ingester (Python) ──> Supabase / PostGIS ──> Dashboard (browser)
  Open511 (BC)        adapters + highway      road_events          MapLibre map +
  IBI/511 (8 prov)    filter + throttle       cameras, conditions  filterable list,
  MTQ WFS (QC)        clear+append batches     facilities + view    facility proximity
```

## What is built

- **Backend ingester** (`backend/`) — 3 source adapters covering all 10 provinces,
  a shared normalizer, a highway filter, a rate limiter, and a Supabase sink.
- **Database** (Supabase project `road-incidents`, region `ca-central-1`) — PostGIS
  schema with `road_events`, `road_conditions`, `cameras`, `facilities`, the
  `relevant_road_events` proximity view, and security-definer ingest RPCs.
- **Frontend dashboard** (`frontend/`) — static MapLibre app reading Supabase via
  the publishable key (read-only, RLS-enforced).
- **Tests** (`backend/tests/`) — 23 offline tests over captured real samples.

### Current data (live load)

| | Rows |
|---|---|
| Facilities | 210 |
| Road events (highways) | 1097 |
| — full closures | 119 |
| Cameras | 1357 |
| Road conditions | 1082 |
| Events near facilities | 224 |

Sources live today: **BC, Alberta, Ontario, Manitoba, Québec**.
Pending API keys (same connector, config-only): **Saskatchewan, NB, NS, PE, NL**.

## Sources & keys

| Province | Platform | API key | Status |
|----------|----------|---------|--------|
| British Columbia | Open511 | none | live |
| Alberta | IBI/511 | none | live |
| Ontario | IBI/511 | none | live |
| Québec | MTQ WFS GeoJSON | none | live |
| Manitoba | IBI/511 | yes (held) | live |
| Saskatchewan | IBI/511 | yes | needs key |
| New Brunswick / Nova Scotia / PEI / Newfoundland | IBI/511 | yes | keys requested |

See [API_INVENTORY.md](API_INVENTORY.md) for endpoints, formats and licensing, and
[docs/SCHEMAS.md](docs/SCHEMAS.md) for raw and normalized data shapes.

## Backend setup

```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env      # then fill SUPABASE_SERVICE_KEY (Dashboard > Settings > API)
```

### Run the ingester

```bash
# Load facilities once (static), then ingest the live sources:
python -m src.ingest.run --facilities ../points_of_interest.csv --push

# Ingest only (default core sources BC/AB/ON/MB/QC):
python -m src.ingest.run --push

# Include key-gated provinces once their keys are in .env:
python -m src.ingest.run --all-sources --push

# Offline / inspection (no DB, no network) — parse captured samples:
python -m src.ingest.run --from-samples samples --out samples/normalized
```

Key flags: `--source <code>` (repeatable), `--all-roads` (keep local roads),
`--no-raw` (omit raw source blob). The ingester respects the IBI 10-calls/60s limit
and writes each source as clear-then-append batches.

### Tests

```bash
cd backend && source .venv/bin/activate && python -m pytest -q
```

## Frontend

Static, no build step. Reads Supabase with the publishable key.

```bash
cd frontend
python3 -m http.server 8765
# open http://localhost:8765/index.html
```

Filters: search, **recency** (default last 24h; 6h/3d/7d/30d/all), **importance**
(default *High priority & up* — hides low-signal construction; *Critical only* or
*Show everything*), near-facilities-only, full-closures-only, scheduled-only, by event
type, by province, and toggles for events / facilities / cameras / road-conditions
layers. **Auto-refresh** (every 5 min, default off). The list is sortable by severity,
nearest facility, or last updated.

Importance tiers: *Critical* = full closures + accidents (always shown, never aged
out, since an ongoing closure may have started weeks ago); *High* = closures,
restrictions, truck-restricted, or near-facility events; *Low* = everything else.

## Security model

- Browser uses the **publishable** key; RLS grants `anon` **SELECT only** on the four
  data tables and the proximity view.
- Writes go only through **security-definer RPCs** granted to **`service_role`**
  (the ingester's secret key) — revoked from `anon`, `authenticated`, `public`.
- Remaining Supabase linter notices (`spatial_ref_sys` RLS, `postgis` in `public`,
  `st_estimatedextent`) are PostGIS extension defaults and are accepted.

## Deployment

Live, all on free tiers:

| Component | Where | URL / notes |
|-----------|-------|-------------|
| Database | Supabase | project `road-incidents` (`jwcfsknwwbnxoiaphtkw`, ca-central-1) |
| Dashboard | Vercel | https://frontend-mateoheras77s-projects.vercel.app |
| Ingester | GitHub Actions | `.github/workflows/ingest.yml`, cron `7,22,37,52 * * * *` (every 15 min) |
| Repo | GitHub (public) | https://github.com/MateoHeras77/road-incidents |

- **Ingester** runs every 15 minutes via GitHub Actions (free, unlimited on public
  repos). GitHub's scheduler is best-effort; the offset 15-min cadence is honored more
  reliably than `*/5`, and a new repo's first scheduled run can lag 1–2h before it
  begins firing. Secrets live in **GitHub Actions Secrets** (`SUPABASE_URL`,
  `SUPABASE_SERVICE_KEY`, `MANITOBA_511_KEY`, + pending provinces). Manual run:
  Actions tab → "Ingest road incidents" → Run workflow (toggle `facilities` to also
  reload the POI CSV).
- **Frontend** redeploy: `vercel deploy --prod --yes --cwd frontend` (Vercel
  deployment protection is disabled so planners can open it without a login).
- One source timing out skips only that source for that run (its rows are left
  untouched); the job fails only on a total outage.

## Licensing caveat

Only BC (OGL-BC), Ontario (OGL-ON) and Québec (CC-BY 4.0) publish clear
redistribution licenses. Alberta, Manitoba and the key-gated provinces publish none —
secure written redistribution permission before any external/public exposure. This is
an internal Middle Mile tool today.
