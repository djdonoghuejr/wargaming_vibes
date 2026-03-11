# Architecture Notes

## Current MVP

The MVP is designed to prove the architecture with hand-authored assets and deterministic simulation before any model integration is introduced.

### Core layers

- `schemas`: stable contracts for every persisted artifact
- `validation`: semantic checks that prevent contradictory assets
- `simulation`: state transitions, adjudication, and scoring
- `analysis`: AARs, lessons, and COA comparisons
- `storage`: JSON and JSONL persistence for reusable datasets
- `cli`: execution entrypoints for validation and demos

## Deliberate design choices

- Operational level, not tactical physics.
- Zone graph map, not detailed geospatial pathing.
- Structured state snapshots, not replaying long natural-language history.
- Deterministic seeded adjudication with bounded randomness.
- Hand-authored seed assets for credibility, then generated assets later.

## Offline vs Runtime

### Offline generation mode

- scenario library generation
- force package generation
- COA generation
- batched simulation and lesson mining
- evaluation corpus creation

### Runtime/demo mode

- load prebuilt structured assets
- run deterministic simulation
- keep prompts short and state-focused
- emit compact JSON outputs and concise summaries
