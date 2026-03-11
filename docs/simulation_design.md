# Simulation Design

## Turn Phases

1. Order intake
2. Recon and passive detection
3. Movement
4. Support and resupply
5. Engagement adjudication
6. Scoring and snapshot persistence

## Action Catalog

- `move`
- `hold`
- `recon`
- `attack`
- `resupply`
- `support`

## Adjudication Principles

- Use structured inputs and deterministic formulas first.
- Use seeded randomness only as bounded friction.
- Emit reason codes on every meaningful event.
- Preserve event logs and turn snapshots as reusable datasets.

## Scoring

Per-side scorecards track:

- objective control
- force preservation
- sustainment
- tempo

Final run scores are weighted by the scenario scoring profile.
