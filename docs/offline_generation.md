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
- prompt templates for scenario, force package, and COA generation
- promotion and quarantine directories under each generation batch

## Intended Next Step

Add a live provider that implements the `GenerationProvider` protocol. The live provider should only be responsible for model invocation. Rendering, archiving, validation, promotion, and quarantine should remain in the pipeline layer.
