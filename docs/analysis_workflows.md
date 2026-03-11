# Analysis Workflows

## Cross-Run Lesson Aggregation

`aggregate-lessons` scans completed run bundles and clusters lessons by shared conditions or tags. This is meant to turn per-run lessons into reusable patterns such as:

- recurring sustainment failures
- repeated defender terrain advantages
- common recon or coordination patterns

The output is written as `lesson_clusters.jsonl` plus a small manifest.

## Run Quality Scoring

`evaluate-runs` scores each run for analytical usefulness. The current heuristics check for:

- sufficient event volume
- presence of attacks and zone changes
- populated AAR highlights
- lesson extraction with evidence links
- a minimally useful end-state contact picture

These scores are not meant to be final truth. They are meant to surface weak or shallow runs before they enter a reusable dataset library.
