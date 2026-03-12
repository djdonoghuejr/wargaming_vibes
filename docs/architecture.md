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
## Stochastic Execution Path

The repository now supports a second execution path alongside fixed handcrafted assets:

- template assets define bounded variability
- a seed-driven sampler materializes concrete runtime assets
- the existing simulation engine executes the realized scenario
- run outputs preserve template lineage and sampled values in `instantiation.json`

This keeps the deterministic baseline intact while moving the long-term architecture toward controlled stochastic experimentation rather than fully fixed scenario playback.

## Catalog Layer

The repository now supports a DuckDB catalog build step that refreshes:

- flat run datasets
- run quality rows
- template quality rows
- template metadata
- comparison summaries

The catalog is intended to become the query layer for selecting approved templates, inspecting experiment history, and comparing outcomes across seeds, COAs, and template families.
