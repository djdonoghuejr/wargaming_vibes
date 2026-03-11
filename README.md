# Operational Experiment Generator

Operational Experiment Generator is a Python toolkit for building structured military-style operational scenarios, simulating turn-based interactions, comparing multiple courses of action, and emitting reusable analytical outputs such as event logs, AARs, and lessons learned.

The repository is intentionally split between:

- offline asset generation that can be token-intensive later
- runtime/demo execution that is deterministic, compact, and cheap

## MVP Status

The current repository implements the first deterministic slice:

- versioned Pydantic schemas for core artifacts
- semantic validation for scenarios, force packages, and COAs
- a turn-based simulation engine with deterministic seeded adjudication
- structured JSON and JSONL outputs for runs and comparisons
- a CLI for validation, single-run execution, and COA comparison

## Quickstart

1. Create a virtual environment and install the package.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
```

2. Validate the bundled sample assets.

```powershell
oeg validate-assets
```

3. Run the sample scenario with one COA.

```powershell
oeg run-scenario --output-dir data/runs
```

4. Compare the two sample blue COAs against the same red COA using paired seeds.

```powershell
oeg compare-coas --seed 11 --seed 22 --seed 33 --output-dir data/runs
```

## Repo Layout

- `src/oeg/schemas`: canonical artifact contracts
- `src/oeg/validation`: semantic and cross-asset checks
- `src/oeg/simulation`: deterministic turn engine and adjudication logic
- `src/oeg/analysis`: AAR, lessons, and COA comparison summarization
- `src/oeg/storage`: JSON, JSONL, and output bundle persistence
- `data`: sample scenarios, force packages, COAs, and generated runs
- `docs`: architecture and simulation notes

## Immediate Next Steps

- add offline generation pipelines for scenarios, force packages, and COAs
- add fog-of-war belief state for runtime planners
- add dataset export and DuckDB cataloging
- add prompt contracts and evaluation harnesses
