# Analyst Console Frontend

## Purpose

The analyst console adds a local React + FastAPI interface over the existing OEG catalog, run artifacts, and batch workflows. It is intentionally analyst-first: browse approved templates, inspect runs and comparisons, review evidence-linked AARs and lessons, instantiate assets, and launch approved batch studies without leaving the console.

## App Boundary

- `src/oeg`
  - core domain library
  - schemas, simulation, sampling, storage, evaluation, workflows
- `apps/api`
  - FastAPI analyst API
  - reads from DuckDB and run JSON bundles
  - invokes library workflows directly for instantiation and batch execution
- `apps/web`
  - React analyst console
  - uses API only
  - does not read files from disk directly

This keeps the API as the contract boundary and avoids duplicating simulation or storage logic in the frontend.

## API Surface

Implemented endpoints:

- `GET /health`
- `GET /catalog/summary`
- `GET /templates`
- `GET /templates/{template_id}`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
- `GET /comparisons`
- `GET /comparisons/{comparison_id}`
- `GET /instantiations/{instantiation_id}`
- `GET /lessons`
- `POST /actions/instantiate`
- `POST /actions/run-batch`
- `GET /actions/jobs/{job_id}`

Read endpoints use DuckDB for list/query work and read JSON run bundles for deeper detail views when that is simpler than further denormalization.

## UI Route Map

- `/`
  - overview cards
  - recent runs, comparisons, approved templates
- `/templates`
  - filterable template explorer
- `/templates/:templateId`
  - template detail, variability summary, related runs/comparisons
- `/runs`
  - filterable run explorer
- `/runs/:runId`
  - run manifest, map, timeline, AAR, lessons, observation frames
- `/comparisons`
  - comparison list
- `/comparisons/:comparisonId`
  - per-COA metric view and linked runs
- `/instantiations/:instantiationId`
  - realized asset bundle from a sampled template instantiation
- `/actions`
  - instantiate approved assets
  - launch approved batch runs
  - poll job status

## Visual Direction

The console uses a light operations-room / paper-map aesthetic rather than a generic SaaS dashboard:

- warm neutrals and muted blue/green accents
- serif heading voice with a denser sans-serif data layer
- map-grid textures and panel depth
- compact metric cards, evidence chips, and turn-phase bands

The UI is desktop-first but remains responsive enough for narrower widths.

## Running The Stack

1. Build or refresh the catalog.

```powershell
oeg build-catalog --runs-dir data/runs --templates-dir data/templates --datasets-dir data/datasets --analysis-dir data/analysis --output-path data/catalog.duckdb
```

2. Start the API.

```powershell
uvicorn apps.api.main:app --reload
```

3. Start the React console.

```powershell
cd apps/web
npm install
npm run dev
```

The web app defaults to `http://127.0.0.1:8000` for API access. Override with `VITE_API_BASE_URL` if needed.

## Testing

Backend:

```powershell
pytest tests/api/test_analyst_api.py
```

Frontend:

```powershell
cd apps/web
npm test
npm run build
```

## Current Limits

- single-user/local use only
- no authentication
- polling job status only, no websocket streaming
- map view uses the existing zone graph rather than geographic rendering
- action endpoints are intentionally narrow: instantiation and approved batch execution only
