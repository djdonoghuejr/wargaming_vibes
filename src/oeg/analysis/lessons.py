from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from oeg.storage.io import ensure_directory
from oeg.storage.io import write_json
from oeg.storage.io import write_jsonl


def aggregate_lessons(runs_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    runs_root = Path(runs_dir)
    output_root = ensure_directory(Path(output_dir))

    clusters: dict[str, dict[str, Any]] = {}
    run_count = 0
    lesson_count = 0

    for run_dir in sorted(item for item in runs_root.iterdir() if item.is_dir() and item.name.startswith("run_")):
        manifest_path = run_dir / "manifest.json"
        lessons_path = run_dir / "lessons.json"
        if not manifest_path.exists() or not lessons_path.exists():
            continue

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        lessons = json.loads(lessons_path.read_text(encoding="utf-8"))
        run_count += 1
        for lesson in lessons:
            lesson_count += 1
            cluster_key = _cluster_key(lesson)
            cluster = clusters.setdefault(
                cluster_key,
                {
                    "cluster_id": cluster_key,
                    "run_ids": [],
                    "lesson_ids": [],
                    "observations": Counter(),
                    "implications": Counter(),
                    "recommended_actions": Counter(),
                    "conditions": Counter(),
                    "tags": Counter(),
                    "confidence_sum": 0.0,
                    "evidence_event_total": 0,
                },
            )
            cluster["run_ids"].append(manifest["id"])
            cluster["lesson_ids"].append(lesson["id"])
            cluster["observations"][lesson["observation"]] += 1
            cluster["implications"][lesson["implication"]] += 1
            cluster["recommended_actions"][lesson["recommended_action"]] += 1
            for condition in lesson.get("conditions", []):
                cluster["conditions"][condition] += 1
            for tag in lesson.get("tags", []):
                cluster["tags"][tag] += 1
            cluster["confidence_sum"] += float(lesson["confidence"])
            cluster["evidence_event_total"] += len(lesson.get("evidence_event_ids", []))

    aggregate_rows = [_flatten_cluster(cluster) for cluster in clusters.values()]
    aggregate_rows.sort(key=lambda row: (row["occurrence_count"], row["mean_confidence"]), reverse=True)

    write_jsonl(output_root / "lesson_clusters.jsonl", aggregate_rows)
    manifest = {
        "run_count": run_count,
        "lesson_count": lesson_count,
        "cluster_count": len(aggregate_rows),
        "source_runs_dir": str(runs_root),
        "output_dir": str(output_root),
    }
    write_json(output_root / "manifest.json", manifest)
    return manifest


def _cluster_key(lesson: dict[str, Any]) -> str:
    conditions = sorted(lesson.get("conditions", []))
    tags = sorted(lesson.get("tags", []))
    return "|".join(conditions or tags or ["uncategorized"])


def _flatten_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    occurrence_count = len(cluster["lesson_ids"])
    unique_runs = sorted(set(cluster["run_ids"]))
    mean_confidence = cluster["confidence_sum"] / max(1, occurrence_count)
    return {
        "cluster_id": cluster["cluster_id"],
        "occurrence_count": occurrence_count,
        "run_count": len(unique_runs),
        "run_ids": unique_runs,
        "lesson_ids": cluster["lesson_ids"],
        "canonical_observation": cluster["observations"].most_common(1)[0][0],
        "canonical_implication": cluster["implications"].most_common(1)[0][0],
        "recommended_action": cluster["recommended_actions"].most_common(1)[0][0],
        "conditions": [item for item, _ in cluster["conditions"].most_common()],
        "tags": [item for item, _ in cluster["tags"].most_common()],
        "mean_confidence": round(mean_confidence, 4),
        "mean_evidence_event_count": round(cluster["evidence_event_total"] / max(1, occurrence_count), 4),
    }
