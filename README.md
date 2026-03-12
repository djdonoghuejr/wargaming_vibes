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
- runtime planners with side-specific state inputs
- an offline generation pipeline with replay and live model-backed providers
- structured JSON and JSONL outputs for runs and comparisons
- cross-run lesson aggregation and run-quality scoring
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

5. Run the runtime-mode demo with heuristic planners.

```powershell
oeg run-runtime-demo --output-dir data/runs
```

6. Replay an offline generation batch from captured raw responses.

```powershell
oeg replay-generation-batch --request-file path/to/requests.json --replay-file path/to/replay.json --output-dir data/generated
```

7. Generate a live offline batch with an OpenAI model.

```powershell
$env:OPENAI_API_KEY = "sk-..."
oeg generate-live-batch --request-file path/to/requests.json --model gpt-5-mini --output-dir data/generated
```

8. Export flat JSONL datasets from completed runs.

```powershell
oeg export-dataset --runs-dir data/runs --output-dir data/datasets
```

9. Aggregate lessons across completed runs.

```powershell
oeg aggregate-lessons --runs-dir data/runs --output-dir data/analysis
```

10. Score completed runs for output quality.

```powershell
oeg evaluate-runs --runs-dir data/runs --output-dir data/analysis
```

## Repo Layout

- `src/oeg/schemas`: canonical artifact contracts
- `src/oeg/planners`: runtime planner interfaces and implementations
- `src/oeg/generators`: offline generation batch scaffolding
- `src/oeg/validation`: semantic and cross-asset checks
- `src/oeg/simulation`: deterministic turn engine and adjudication logic
- `src/oeg/analysis`: AAR, lessons, and COA comparison summarization
- `src/oeg/evaluation`: run-quality scoring and evaluation utilities
- `src/oeg/storage`: JSON, JSONL, and output bundle persistence
- `prompts/offline`: versioned prompt templates for later model-backed generation
- `data`: sample scenarios, force packages, COAs, and generated runs
- `docs`: architecture and simulation notes

## Immediate Next Steps

- deepen fog-of-war mechanics and planner-side belief state
- add dataset export and DuckDB cataloging
- add prompt contracts and evaluation harnesses
- add a lightweight run viewer over exported datasets
