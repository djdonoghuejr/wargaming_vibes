from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oeg.storage.io import ensure_directory
from oeg.storage.io import write_json
from oeg.storage.io import write_jsonl


def evaluate_runs(runs_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    runs_root = Path(runs_dir)
    output_root = ensure_directory(Path(output_dir))

    rows: list[dict[str, Any]] = []
    for run_dir in sorted(item for item in runs_root.iterdir() if item.is_dir() and item.name.startswith("run_")):
        manifest_path = run_dir / "manifest.json"
        aar_path = run_dir / "aar.json"
        lessons_path = run_dir / "lessons.json"
        events_path = run_dir / "event_log.jsonl"
        final_state_path = run_dir / "final_state.json"
        if not manifest_path.exists() or not events_path.exists():
            continue

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        aar = json.loads(aar_path.read_text(encoding="utf-8")) if aar_path.exists() else {}
        lessons = json.loads(lessons_path.read_text(encoding="utf-8")) if lessons_path.exists() else []
        final_state = json.loads(final_state_path.read_text(encoding="utf-8")) if final_state_path.exists() else {}
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        rows.append(_score_run(manifest, aar, lessons, final_state, events))

    write_jsonl(output_root / "run_quality_rows.jsonl", rows)
    summary = {
        "run_count": len(rows),
        "pass_count": sum(1 for row in rows if row["quality_band"] in {"good", "strong"}),
        "warning_count": sum(1 for row in rows if row["quality_band"] == "warning"),
        "fail_count": sum(1 for row in rows if row["quality_band"] == "weak"),
        "output_dir": str(output_root),
        "source_runs_dir": str(runs_root),
    }
    write_json(output_root / "manifest.json", summary)
    return summary


def _score_run(
    manifest: dict[str, Any],
    aar: dict[str, Any],
    lessons: list[dict[str, Any]],
    final_state: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    warnings: list[str] = []
    score = 1.0

    if len(events) < 5:
        score -= 0.2
        warnings.append("Very few events were logged.")

    attack_events = [event for event in events if event["action_type"] == "attack"]
    if not attack_events:
        score -= 0.15
        warnings.append("No attack events occurred; the run may be analytically shallow.")

    zone_change_count = sum(1 for event in events if event["adjudication"]["zone_control_change"])
    if zone_change_count == 0:
        score -= 0.1
        warnings.append("No zone control changes occurred.")

    if not aar.get("timeline_highlights"):
        score -= 0.1
        warnings.append("AAR contains no timeline highlights.")

    if not lessons:
        score -= 0.15
        warnings.append("No lessons were extracted.")

    weak_evidence = [lesson for lesson in lessons if len(lesson.get("evidence_event_ids", [])) == 0]
    if weak_evidence:
        score -= 0.1
        warnings.append("One or more lessons lack evidence event references.")

    blue_score = manifest["summary_scores"]["blue"]["overall_score"]
    red_score = manifest["summary_scores"]["red"]["overall_score"]
    if abs(blue_score - red_score) < 0.01:
        score -= 0.05
        warnings.append("Outcome delta is very narrow; recommendation confidence may be weak.")

    blue_view = final_state.get("side_views", {}).get("blue", {})
    red_view = final_state.get("side_views", {}).get("red", {})
    if not blue_view.get("known_enemy_positions") and not blue_view.get("suspected_enemy_zones"):
        score -= 0.05
        warnings.append("Blue ended with almost no usable contact picture.")
    if not red_view.get("known_enemy_positions") and not red_view.get("suspected_enemy_zones"):
        score -= 0.05
        warnings.append("Red ended with almost no usable contact picture.")

    score = max(0.0, round(score, 4))
    if score >= 0.85:
        band = "strong"
    elif score >= 0.7:
        band = "good"
    elif score >= 0.5:
        band = "warning"
    else:
        band = "weak"

    return {
        "run_id": manifest["id"],
        "scenario_id": manifest["scenario_id"],
        "blue_actor_id": manifest["blue_coa_id"],
        "red_actor_id": manifest["red_coa_id"],
        "seed": manifest["seed"],
        "quality_score": score,
        "quality_band": band,
        "event_count": len(events),
        "attack_event_count": len(attack_events),
        "zone_control_change_count": zone_change_count,
        "lesson_count": len(lessons),
        "timeline_highlight_count": len(aar.get("timeline_highlights", [])),
        "warnings": warnings,
    }
