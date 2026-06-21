# Canadian Road Closures — API Inventory

Goal: consolidate road closure / road condition data from all Canadian provincial
511 sites into a single local application.

Last updated: 2026-06-20

> **Status:** Built and live for BC, Alberta, Ontario, Manitoba and Québec — ingester
> + Supabase/PostGIS + dashboard. See [README.md](README.md). This file is the API
> reference; [docs/SCHEMAS.md](docs/SCHEMAS.md) documents the data shapes.

## Backend platforms

All 10 provincial sites fall into 3 families:

1. **Open511** (open standard) — British Columbia only. JSON + XML. No key.
2. **"511" platform (IBI Group / Castle Rock)** — AB, SK, ON, MB, NB, NS, PE, NL.
   Shared API contract: `https://<host>/api/v2/get/<resource>?format=json&lang=en`.
   Some hosts require a free API key, some do not.
3. **MTQ open data (WFS / GeoJSON)** — Québec only. No key. CC-BY 4.0.

One ingester can cover all family-2 provinces by swapping host + key.

## API key status

| Province | Host | API key required | Key / status |
|----------|------|------------------|--------------|
| British Columbia | api.open511.gov.bc.ca | No | Ready |
| Alberta | 511.alberta.ca | No | Ready |
| Saskatchewan | hotline.gov.sk.ca | Yes | TODO — register at /my511/register (corrected: returns "Invalid Key" without one) |
| Ontario | 511on.ca | No | Ready |
| Québec | ws.mapserver.transports.gouv.qc.ca | No | Ready |
| Manitoba | www.manitoba511.ca | Yes | held (stored in GitHub Secrets / local `.env`) |
| New Brunswick | 511.gnb.ca | Yes | TODO — register at /my511/register |
| Nova Scotia | 511.novascotia.ca | Yes | TODO — register at /my511/register |
| PEI | 511.gov.pe.ca | Yes | TODO — register at /my511/register |
| Newfoundland | 511nl.ca | Yes | TODO — register at /my511/register |

## Endpoints by province

### British Columbia (Open511)

- Base: `https://api.open511.gov.bc.ca/`
- Events/closures: `https://api.open511.gov.bc.ca/events?format=json&limit=500`
- Areas: `https://api.open511.gov.bc.ca/areas`
- Docs: https://api.open511.gov.bc.ca/help
- Format: Open511 JSON/XML. Pagination via `limit`/`offset` (max 500/call).
- Cameras: separate draft API (github.com/bcgov/drivebc-webcam-api), not in Open511 feed.
- License: Open Government Licence – British Columbia (redistribution with attribution).

### "511" platform — common contract (AB, SK, ON, MB, NB, NS, PE, NL)

- Pattern: `https://<host>/api/v2/get/<resource>?format=json&lang=en`
  (also `format=xml`, `lang=fr`; a `v3` family exists for some resources)
- Resources: `event`, `roadconditions` / `winterroads`, `cameras`, `ferries`,
  `advisories` (availability varies by province).
- Per-resource docs: `https://<host>/help/endpoint/<resource>`
- API docs index: `https://<host>/developers/doc`
- Rate limit: **10 calls per 60 seconds** (per key). Cache server-side; do not
  proxy live per visitor.
- Format: JSON or XML (NOT GeoJSON). Geometry as Latitude/Longitude + Google
  EncodedPolyline.

Event fields: `ID, RoadwayName, DirectionOfTravel, Description, EventType,
EventSubType, LanesAffected, IsFullClosure, Severity, Latitude, Longitude,
EncodedPolyline, StartDate, PlannedEndDate, Restrictions{Width,Height,Weight,Speed},
DetourPolyline, DetourInstructions, Recurrence`.

Per-host notes:
- Alberta: no key. Winter conditions under `api/v3/get/winterroads`. Host mirror ab.ibi511.com.
- Saskatchewan: no key. Resources include iceroads. Host hotline.gov.sk.ca.
- Ontario: no key. License: Open Government Licence – Ontario (attribution + 511 logo).
- Manitoba: key required (have it). Resources include winterroads, "Track My Plow".
- New Brunswick: key required. Resources: road conditions, cameras, ferries, events, advisories.
- Nova Scotia: key required. Developer docs page 404, but API is live (same contract).
- PEI: key required. Extra resource: Parks.
- Newfoundland: key required. Extra resource: Wreckhouse Wind Warnings.

### Québec (MTQ open data — WFS / GeoJSON)

- Road warnings / closures / incidents (Avertissement routier):
  `https://ws.mapserver.transports.gouv.qc.ca/swtq?service=wfs&version=2.0.0&request=getfeature&typename=ms:evenements&outfile=AvertissementRoutier&srsname=EPSG:4326&outputformat=geojson`
- Winter road conditions (Condition routière hivernale):
  `https://ws.mapserver.transports.gouv.qc.ca/swtq?service=wfs&version=2.0.0&request=getfeature&typename=ms:conditions_routieres&outfile=CondRoutHiver_Continu&srsname=EPSG:4326&outputformat=geojson`
- Formats: GeoJSON, CSV, SHP, GeoPackage, plus OGC WFS/WMS (getcapabilities).
- No key, anonymous HTTP GET.
- License: Creative Commons Attribution 4.0 (CC-BY 4.0).
- Dataset pages:
  - https://www.donneesquebec.ca/recherche/dataset/avertissement-routier
  - https://www.donneesquebec.ca/recherche/dataset/condition-routiere-hivernale-du-reseau-routier-mtq

## Licensing (redistribution)

| Province | License | Redistribution |
|----------|---------|----------------|
| British Columbia | OGL-BC | OK with attribution |
| Ontario | OGL-Ontario | OK with attribution + 511 logo |
| Québec | CC-BY 4.0 | OK with attribution |
| Alberta, Saskatchewan, Manitoba, NB, NS, PE, NL | None published | Confirm in writing before publishing |

Technical access is free everywhere; the open blocker is redistribution rights for
the 7 provinces with no published license. Get written permission before any public launch.

## Open TODOs

- [ ] Register and obtain API keys: NB, NS, PE, NL.
- [ ] Confirm written redistribution permission: AB, SK, MB, NB, NS, PE, NL.
- [ ] Verify live endpoints + capture sample payloads (BC, AB, SK, ON, QC done first; keyed ones after).
- [ ] Design normalized schema across the 3 platform families.
- [ ] Build ingester (Python + uv) with caching and 10 req/60s throttle handling.
