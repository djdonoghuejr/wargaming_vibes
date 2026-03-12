from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oeg.storage.io import ensure_directory
from oeg.storage.io import write_json
from oeg.storage.io import write_jsonl


def export_run_dataset(runs_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    runs_root = Path(runs_dir)
    dataset_root = ensure_directory(Path(output_dir))

    run_rows: list[dict[str, Any]] = []
    aar_rows: list[dict[str, Any]] = []
    lesson_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    instantiation_rows: list[dict[str, Any]] = []

    for run_dir in sorted(item for item in runs_root.iterdir() if item.is_dir() and item.name.startswith("run_")):
        manifest_path = run_dir / "manifest.json"
        aar_path = run_dir / "aar.json"
        lessons_path = run_dir / "lessons.json"
        event_log_path = run_dir / "event_log.jsonl"
        instantiation_path = run_dir / "instantiation.json"
        if not manifest_path.exists():
            continue

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        run_rows.append(_flatten_manifest(manifest))

        if aar_path.exists():
            aar = json.loads(aar_path.read_text(encoding="utf-8"))
            aar_rows.append(_flatten_aar(aar))

        if lessons_path.exists():
            lessons = json.loads(lessons_path.read_text(encoding="utf-8"))
            for lesson in lessons:
                lesson_rows.append(_flatten_lesson(manifest["id"], lesson))

        if event_log_path.exists():
            for line in event_log_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                event_rows.append(_flatten_event(manifest["id"], event))

        if instantiation_path.exists():
            instantiation = json.loads(instantiation_path.read_text(encoding="utf-8"))
            instantiation_rows.append(_flatten_instantiation(instantiation))

    write_jsonl(dataset_root / "run_manifest_rows.jsonl", run_rows)
    write_jsonl(dataset_root / "aar_rows.jsonl", aar_rows)
    write_jsonl(dataset_root / "lesson_rows.jsonl", lesson_rows)
    write_jsonl(dataset_root / "event_rows.jsonl", event_rows)
    write_jsonl(dataset_root / "instantiation_rows.jsonl", instantiation_rows)

    manifest = {
        "run_count": len(run_rows),
        "aar_count": len(aar_rows),
        "lesson_count": len(lesson_rows),
        "event_count": len(event_rows),
        "instantiation_count": len(instantiation_rows),
        "source_runs_dir": str(runs_root),
        "output_dir": str(dataset_root),
    }
    write_json(dataset_root / "manifest.json", manifest)
    return manifest


def _flatten_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    blue = manifest["summary_scores"]["blue"]
    red = manifest["summary_scores"]["red"]
    return {
        "run_id": manifest["id"],
        "scenario_id": manifest["scenario_id"],
        "blue_force_package_id": manifest["blue_force_package_id"],
        "red_force_package_id": manifest["red_force_package_id"],
        "blue_actor_id": manifest["blue_coa_id"],
        "red_actor_id": manifest["red_coa_id"],
        "seed": manifest["seed"],
        "instantiation_id": manifest.get("instantiation_id"),
        "stochastic_profile_id": manifest.get("stochastic_profile_id"),
        "source_scenario_template_id": manifest.get("source_scenario_template_id"),
        "source_blue_force_template_id": manifest.get("source_blue_force_template_id"),
        "source_red_force_template_id": manifest.get("source_red_force_template_id"),
        "source_blue_coa_template_id": manifest.get("source_blue_coa_template_id"),
        "source_red_coa_template_id": manifest.get("source_red_coa_template_id"),
        "turns_completed": manifest["turns_completed"],
        "final_outcome": manifest["final_outcome"],
        "blue_overall_score": blue["overall_score"],
        "red_overall_score": red["overall_score"],
        "blue_objective_control": blue["objective_control"],
        "red_objective_control": red["objective_control"],
        "blue_force_preservation": blue["force_preservation"],
        "red_force_preservation": red["force_preservation"],
        "blue_sustainment": blue["sustainment"],
        "red_sustainment": red["sustainment"],
        "blue_tempo": blue["tempo"],
        "red_tempo": red["tempo"],
    }


def _flatten_aar(aar: dict[str, Any]) -> dict[str, Any]:
    return {
        "aar_id": aar["id"],
        "run_id": aar["run_id"],
        "scenario_id": aar["scenario_id"],
        "mission_outcome": aar["mission_outcome"],
        "timeline_highlight_count": len(aar.get("timeline_highlights", [])),
        "key_decision_count": len(aar.get("key_decisions", [])),
        "causal_factor_count": len(aar.get("causal_factors", [])),
        "recommended_action_count": len(aar.get("recommended_actions", [])),
    }


def _flatten_lesson(run_id: str, lesson: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "lesson_id": lesson["id"],
        "observation": lesson["observation"],
        "implication": lesson["implication"],
        "recommended_action": lesson["recommended_action"],
        "confidence": lesson["confidence"],
        "conditions": lesson.get("conditions", []),
        "tags": lesson.get("tags", []),
        "evidence_event_count": len(lesson.get("evidence_event_ids", [])),
    }


def _flatten_event(run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    adjudication = event["adjudication"]
    return {
        "run_id": run_id,
        "event_id": event["id"],
        "turn": event["turn"],
        "phase": event["phase"],
        "actor_side": event["actor_side"],
        "action_type": event["action_type"],
        "target_zone": event.get("target_zone"),
        "combat_result": adjudication["combat_result"],
        "zone_control_change": adjudication["zone_control_change"],
        "blue_losses": adjudication["blue_losses"],
        "red_losses": adjudication["red_losses"],
        "reason_codes": adjudication.get("reason_codes", []),
        "confidence": event["confidence"],
    }


def _flatten_instantiation(instantiation: dict[str, Any]) -> dict[str, Any]:
    component_seeds = instantiation.get("sampled_values", {}).get("component_seeds", {})
    return {
        "instantiation_id": instantiation["id"],
        "seed": instantiation["seed"],
        "stochastic_profile_id": instantiation["stochastic_profile_id"],
        "scenario_template_id": instantiation["scenario_template_id"],
        "blue_force_template_id": instantiation["blue_force_template_id"],
        "red_force_template_id": instantiation["red_force_template_id"],
        "blue_coa_template_id": instantiation["blue_coa_template_id"],
        "red_coa_template_id": instantiation["red_coa_template_id"],
        "scenario_id": instantiation["scenario_id"],
        "blue_force_package_id": instantiation["blue_force_package_id"],
        "red_force_package_id": instantiation["red_force_package_id"],
        "blue_coa_id": instantiation["blue_coa_id"],
        "red_coa_id": instantiation["red_coa_id"],
        "scenario_component_seed": component_seeds.get("scenario"),
        "blue_force_component_seed": component_seeds.get("blue_force"),
        "red_force_component_seed": component_seeds.get("red_force"),
        "blue_coa_component_seed": component_seeds.get("blue_coa"),
        "red_coa_component_seed": component_seeds.get("red_coa"),
    }
