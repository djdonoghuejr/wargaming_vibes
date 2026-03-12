# Offline Generation Notes

## Purpose

The offline generation layer is where token-intensive work should happen. Its job is to:

- render role-specific prompt templates
- archive raw prompts and raw responses
- parse generated JSON into canonical schemas
- validate outputs semantically before promotion
- quarantine invalid or contradictory artifacts for review

## Current MVP

The current implementation includes:

- `OfflineGenerationPipeline` for batch processing
- replay-based providers for deterministic testing and manual promotion
- a live OpenAI-backed provider using the Responses API
- prompt templates for scenario, force package, and COA generation
- promotion and quarantine directories under each generation batch

## Live Batch Usage

Set `OPENAI_API_KEY` in your shell, then run:

```powershell
oeg generate-live-batch --request-file path/to/requests.json --model gpt-5-mini --output-dir data/generated
```

The live provider only handles model invocation. Rendering, raw prompt/response archiving, semantic validation, promotion, and quarantine still live in the pipeline layer.

## Request File Shape

Request files can be either a JSON array or an object with a top-level `requests` field. Each item should match `GenerationRequest`:

```json
[
  {
    "request_id": "scenario_batch",
    "asset_kind": "scenario",
    "template_path": "prompts/offline/scenario_architect.md",
    "count": 3,
    "context": {
      "scenario_family": "corridor_delay",
      "theme": "screen-and-delay",
      "blue_posture": "defense",
      "red_posture": "assault",
      "turn_count": 6
    }
  }
]
```

For `force_package` and `coa` requests, include the supporting asset paths in `validation_context` so the generated artifact can be checked semantically before promotion.
