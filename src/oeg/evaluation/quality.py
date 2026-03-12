from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from oeg.schemas.models import COATemplate
from oeg.schemas.models import ForceTemplate
from oeg.schemas.models import ScenarioTemplate
from oeg.storage.io import ensure_directory
from oeg.storage.io import write_json
from oeg.storage.io import write_jsonl
from oeg.validation.semantic import SemanticValidationError
from oeg.validation.semantic import validate_coa_template_semantics
from oeg.validation.semantic import validate_force_template_semantics
from oeg.validation.semantic import validate_scenario_template_semantics


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


def evaluate_templates(templates_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    templates_root = Path(templates_dir)
    output_root = ensure_directory(Path(output_dir))

    scenario_templates = _load_templates(
        templates_root / "scenarios",
        ScenarioTemplate,
    )
    force_templates = _load_templates(
        templates_root / "force_packages",
        ForceTemplate,
    )
    coa_templates = _load_templates(
        templates_root / "coas",
        COATemplate,
    )

    rows: list[dict[str, Any]] = []
    rows.extend(_score_scenario_templates(scenario_templates))
    rows.extend(_score_force_templates(force_templates, scenario_templates))
    rows.extend(_score_coa_templates(coa_templates, scenario_templates, force_templates))

    write_jsonl(output_root / "template_quality_rows.jsonl", rows)
    summary = {
        "template_count": len(rows),
        "approved_for_batch_count": sum(1 for row in rows if row["approval_state"] == "approved_for_batch"),
        "promoted_count": sum(1 for row in rows if row["approval_state"] == "promoted"),
        "quarantined_count": sum(1 for row in rows if row["approval_state"] == "quarantined"),
        "source_templates_dir": str(templates_root),
        "output_dir": str(output_root),
    }
    write_json(output_root / "template_manifest.json", summary)
    write_json(
        output_root / "template_approval_manifest.json",
        {
            "approved_for_batch": [row["template_id"] for row in rows if row["approval_state"] == "approved_for_batch"],
            "promoted": [row["template_id"] for row in rows if row["approval_state"] == "promoted"],
            "quarantined": [row["template_id"] for row in rows if row["approval_state"] == "quarantined"],
        },
    )
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


def _load_templates(template_dir: Path, model_cls):
    templates: list[tuple[Path, Any]] = []
    if not template_dir.exists():
        return templates

    for path in sorted(item for item in template_dir.iterdir() if item.is_file() and item.suffix == ".json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            templates.append((path, model_cls.model_validate(payload)))
        except (json.JSONDecodeError, ValidationError):
            templates.append((path, None))
    return templates


def _score_scenario_templates(
    scenario_templates: list[tuple[Path, ScenarioTemplate | None]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    duplicate_counts = _duplicate_name_counts(
        [template.id for _, template in scenario_templates if template is not None]
    )
    for path, template in scenario_templates:
        warnings: list[str] = []
        score = 1.0
        variability_axes = 0

        if template is None:
            rows.append(
                _template_row(
                    path=path,
                    template_id=path.stem,
                    template_kind="scenario_template",
                    quality_score=0.0,
                    quality_band="weak",
                    approval_state="quarantined",
                    warnings=["Template could not be parsed into ScenarioTemplate."],
                )
            )
            continue

        try:
            validate_scenario_template_semantics(template)
        except SemanticValidationError as exc:
            warnings.extend(exc.errors)
            score -= 0.45

        if template.weather_options:
            variability_axes += 1
            if len(template.weather_options) < 2:
                score -= 0.05
                warnings.append("Weather variation exists but has fewer than two options.")
        if template.visibility_options:
            variability_axes += 1
            if len(template.visibility_options) < 2:
                score -= 0.05
                warnings.append("Visibility variation exists but has fewer than two options.")
        if template.zone_strategic_value_adjustments:
            variability_axes += 1
            narrow_ranges = [
                zone_id
                for zone_id, range_value in template.zone_strategic_value_adjustments.items()
                if abs(range_value.max_value - range_value.min_value) < 0.25
            ]
            if narrow_ranges:
                score -= 0.05
                warnings.append(
                    f"Strategic value adjustments are very narrow for zones {sorted(narrow_ranges)}."
                )

        if variability_axes == 0:
            score -= 0.3
            warnings.append("Template defines no meaningful variability axes.")
        elif variability_axes == 1:
            score -= 0.1
            warnings.append("Template only varies along one axis.")

        if duplicate_counts[template.id] > 1:
            score -= 0.1
            warnings.append("Template id appears more than once in the evaluated set.")

        final_score = max(0.0, round(score, 4))
        rows.append(
            _template_row(
                path=path,
                template_id=template.id,
                template_kind="scenario_template",
                quality_score=final_score,
                quality_band=_quality_band(final_score),
                approval_state=_approval_state(final_score),
                warnings=warnings,
                extra={
                    "base_asset_id": template.base_scenario.id,
                    "variability_axis_count": variability_axes,
                },
            )
        )
    return rows


def _score_force_templates(
    force_templates: list[tuple[Path, ForceTemplate | None]],
    scenario_templates: list[tuple[Path, ScenarioTemplate | None]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    scenario_template = next((template for _, template in scenario_templates if template is not None), None)
    duplicate_counts = _duplicate_name_counts(
        [template.id for _, template in force_templates if template is not None]
    )
    for path, template in force_templates:
        warnings: list[str] = []
        score = 1.0
        varied_units = 0
        location_option_units = 0

        if template is None:
            rows.append(
                _template_row(
                    path=path,
                    template_id=path.stem,
                    template_kind="force_template",
                    quality_score=0.0,
                    quality_band="weak",
                    approval_state="quarantined",
                    warnings=["Template could not be parsed into ForceTemplate."],
                )
            )
            continue

        if scenario_template is None:
            warnings.append("No scenario template available for semantic validation.")
            score -= 0.25
        else:
            try:
                validate_force_template_semantics(scenario_template, template)
            except SemanticValidationError as exc:
                warnings.extend(exc.errors)
                score -= 0.45

        for variation in template.unit_variability:
            unit_changed = any(
                getattr(variation, field_name) is not None
                for field_name in ("readiness", "morale", "supply", "signature", "strength", "fatigue")
            )
            if variation.location_options:
                location_option_units += 1
                unit_changed = True
            if unit_changed:
                varied_units += 1

        if varied_units == 0:
            score -= 0.35
            warnings.append("Template defines no unit-level variability.")
        elif varied_units == 1:
            score -= 0.1
            warnings.append("Only one unit varies in the template.")

        if location_option_units == 0:
            score -= 0.05
            warnings.append("No unit start-position variation is defined.")

        if duplicate_counts[template.id] > 1:
            score -= 0.1
            warnings.append("Template id appears more than once in the evaluated set.")

        final_score = max(0.0, round(score, 4))
        rows.append(
            _template_row(
                path=path,
                template_id=template.id,
                template_kind="force_template",
                quality_score=final_score,
                quality_band=_quality_band(final_score),
                approval_state=_approval_state(final_score),
                warnings=warnings,
                extra={
                    "base_asset_id": template.base_force.id,
                    "side": template.side.value,
                    "varied_unit_count": varied_units,
                    "location_option_unit_count": location_option_units,
                },
            )
        )
    return rows


def _score_coa_templates(
    coa_templates: list[tuple[Path, COATemplate | None]],
    scenario_templates: list[tuple[Path, ScenarioTemplate | None]],
    force_templates: list[tuple[Path, ForceTemplate | None]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    scenario_template = next((template for _, template in scenario_templates if template is not None), None)
    force_by_side = {
        template.side.value: template
        for _, template in force_templates
        if template is not None
    }
    duplicate_base_counts = Counter(
        template.base_coa.id
        for _, template in coa_templates
        if template is not None
    )
    for path, template in coa_templates:
        warnings: list[str] = []
        score = 1.0
        variation_count = 0
        distinct_option_count = 0

        if template is None:
            rows.append(
                _template_row(
                    path=path,
                    template_id=path.stem,
                    template_kind="coa_template",
                    quality_score=0.0,
                    quality_band="weak",
                    approval_state="quarantined",
                    warnings=["Template could not be parsed into COATemplate."],
                )
            )
            continue

        force_template = force_by_side.get(template.side.value)
        if scenario_template is None or force_template is None:
            warnings.append("Missing scenario or force template for COA semantic validation.")
            score -= 0.25
        else:
            try:
                validate_coa_template_semantics(scenario_template, force_template, template)
            except SemanticValidationError as exc:
                warnings.extend(exc.errors)
                score -= 0.45

        base_actions = {
            (action.turn, action.unit_id): action
            for action in template.base_coa.actions
        }
        for variation in template.action_variations:
            variation_count += 1
            base_action = base_actions.get((variation.turn, variation.unit_id))
            meaningful_options = 0
            for option in variation.options:
                changed = (
                    base_action is None
                    or option.action != base_action.action
                    or option.target_zone != base_action.target_zone
                    or option.support_unit_ids != base_action.support_unit_ids
                )
                if changed:
                    meaningful_options += 1
            distinct_option_count += meaningful_options
            if meaningful_options == 0:
                score -= 0.12
                warnings.append(
                    f"Variation for turn {variation.turn}, unit {variation.unit_id} does not materially differ from the base COA."
                )

        if variation_count == 0:
            score -= 0.35
            warnings.append("Template defines no action variation.")
        elif variation_count == 1:
            score -= 0.1
            warnings.append("Template only varies one decision point.")

        if distinct_option_count == 0 and variation_count > 0:
            score -= 0.15
            warnings.append("All variation options collapse to the same decision pattern as the base COA.")

        if duplicate_base_counts[template.base_coa.id] > 1:
            score -= 0.05
            warnings.append("Multiple templates share the same base COA id; check for near-duplicates.")

        final_score = max(0.0, round(score, 4))
        rows.append(
            _template_row(
                path=path,
                template_id=template.id,
                template_kind="coa_template",
                quality_score=final_score,
                quality_band=_quality_band(final_score),
                approval_state=_approval_state(final_score),
                warnings=warnings,
                extra={
                    "base_asset_id": template.base_coa.id,
                    "side": template.side.value,
                    "variation_count": variation_count,
                    "distinct_option_count": distinct_option_count,
                },
            )
        )
    return rows


def _template_row(
    *,
    path: Path,
    template_id: str,
    template_kind: str,
    quality_score: float,
    quality_band: str,
    approval_state: str,
    warnings: list[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "template_id": template_id,
        "template_kind": template_kind,
        "template_path": str(path),
        "quality_score": quality_score,
        "quality_band": quality_band,
        "approval_state": approval_state,
        "warning_count": len(warnings),
        "warnings": warnings,
    }
    if extra:
        row.update(extra)
    return row


def _duplicate_name_counts(values: list[str]) -> Counter:
    return Counter(values)


def _quality_band(score: float) -> str:
    if score >= 0.85:
        return "strong"
    if score >= 0.7:
        return "good"
    if score >= 0.5:
        return "warning"
    return "weak"


def _approval_state(score: float) -> str:
    if score >= 0.7:
        return "approved_for_batch"
    if score >= 0.5:
        return "promoted"
    return "quarantined"
