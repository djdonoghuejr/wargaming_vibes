from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

import typer

from oeg.analysis.reporting import aggregate_comparison
from oeg.generators import FileReplayGenerationProvider
from oeg.generators import GenerationRequest
from oeg.generators import OfflineGenerationPipeline
from oeg.paths import default_datasets_dir
from oeg.paths import default_generated_dir
from oeg.paths import default_runs_dir
from oeg.paths import sample_blue_coa_a_path
from oeg.paths import sample_blue_coa_b_path
from oeg.paths import sample_blue_force_path
from oeg.paths import sample_red_coa_path
from oeg.paths import sample_red_force_path
from oeg.paths import sample_scenario_path
from oeg.planners import COAPlanner
from oeg.planners import HeuristicPlanner
from oeg.planners import Planner
from oeg.schemas.models import COA
from oeg.schemas.models import ForcePackage
from oeg.schemas.models import Scenario
from oeg.schemas.models import Side
from oeg.simulation.engine import run_scenario
from oeg.simulation.engine import run_scenario_with_planners
from oeg.storage.io import load_model
from oeg.storage.io import persist_comparison_bundle
from oeg.storage.io import persist_run_bundle
from oeg.storage.export import export_run_dataset
from oeg.validation.semantic import SemanticValidationError
from oeg.validation.semantic import validate_asset_bundle
from oeg.validation.semantic import validate_coa_semantics
from oeg.validation.semantic import validate_force_package_semantics
from oeg.validation.semantic import validate_scenario_semantics


app = typer.Typer(help="Operational Experiment Generator CLI")


class PlannerMode(str, Enum):
    HEURISTIC = "heuristic"
    COA = "coa"


def _default_blue_coas() -> list[Path]:
    return [sample_blue_coa_a_path(), sample_blue_coa_b_path()]


def _load_bundle(
    scenario_path: Path,
    blue_force_path: Path,
    red_force_path: Path,
    blue_coa_paths: list[Path],
    red_coa_path: Path,
) -> tuple[Scenario, ForcePackage, ForcePackage, list[COA], COA]:
    scenario = load_model(scenario_path, Scenario)
    blue_force = load_model(blue_force_path, ForcePackage)
    red_force = load_model(red_force_path, ForcePackage)
    blue_coas = [load_model(path, COA) for path in blue_coa_paths]
    red_coa = load_model(red_coa_path, COA)
    validate_asset_bundle(scenario, blue_force, red_force, blue_coas, red_coa)
    return scenario, blue_force, red_force, blue_coas, red_coa


def _echo_validation_failure(exc: SemanticValidationError) -> None:
    typer.echo("Asset validation failed:")
    for item in exc.errors:
        typer.echo(f"- {item}")


def _load_runtime_assets(
    scenario_path: Path,
    blue_force_path: Path,
    red_force_path: Path,
) -> tuple[Scenario, ForcePackage, ForcePackage]:
    scenario = load_model(scenario_path, Scenario)
    blue_force = load_model(blue_force_path, ForcePackage)
    red_force = load_model(red_force_path, ForcePackage)
    validate_scenario_semantics(scenario)
    validate_force_package_semantics(scenario, blue_force)
    validate_force_package_semantics(scenario, red_force)
    return scenario, blue_force, red_force


def _build_runtime_planner(
    side: Side,
    mode: PlannerMode,
    scenario: Scenario,
    force_package: ForcePackage,
    coa_path: Path,
) -> Planner:
    if mode == PlannerMode.HEURISTIC:
        return HeuristicPlanner(name=f"{side.value}_heuristic")

    coa = load_model(coa_path, COA)
    validate_coa_semantics(scenario, force_package, coa)
    return COAPlanner(coa)


def _load_generation_requests(request_file: Path) -> list[GenerationRequest]:
    raw = json.loads(request_file.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "requests" in raw:
        request_items = raw["requests"]
    elif isinstance(raw, list):
        request_items = raw
    else:
        raise ValueError("Generation request file must be a JSON array or an object with a 'requests' field.")
    return [GenerationRequest.model_validate(item) for item in request_items]


@app.command("validate-assets")
def validate_assets(
    scenario: Path = typer.Option(sample_scenario_path(), exists=True, resolve_path=True),
    blue_force: Path = typer.Option(sample_blue_force_path(), exists=True, resolve_path=True),
    red_force: Path = typer.Option(sample_red_force_path(), exists=True, resolve_path=True),
    blue_coa: list[Path] | None = typer.Option(None, exists=True, resolve_path=True),
    red_coa: Path = typer.Option(sample_red_coa_path(), exists=True, resolve_path=True),
) -> None:
    blue_coa_paths = blue_coa or _default_blue_coas()
    try:
        scenario_obj, _, _, blue_coas, _ = _load_bundle(
            scenario,
            blue_force,
            red_force,
            blue_coa_paths,
            red_coa,
        )
    except SemanticValidationError as exc:
        _echo_validation_failure(exc)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Validation passed for scenario '{scenario_obj.name}' "
        f"with {len(blue_coas)} blue COA(s)."
    )


@app.command("replay-generation-batch")
def replay_generation_batch(
    request_file: Path = typer.Option(..., exists=True, resolve_path=True),
    replay_file: Path = typer.Option(..., exists=True, resolve_path=True),
    output_dir: Path = typer.Option(default_generated_dir(), resolve_path=True),
) -> None:
    try:
        requests = _load_generation_requests(request_file)
        provider = FileReplayGenerationProvider(replay_file)
        pipeline = OfflineGenerationPipeline(output_dir)
        result = pipeline.run_batch(requests, provider)
    except (ValueError, SemanticValidationError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"Generation batch complete: {result.batch_id}")
    typer.echo(
        f"Promoted={result.promoted_count} quarantined={result.quarantined_count}"
    )
    typer.echo(f"Output directory: {output_dir / result.batch_id}")


@app.command("export-dataset")
def export_dataset(
    runs_dir: Path = typer.Option(default_runs_dir(), exists=True, resolve_path=True),
    output_dir: Path = typer.Option(default_datasets_dir(), resolve_path=True),
) -> None:
    manifest = export_run_dataset(runs_dir, output_dir)
    typer.echo(
        f"Dataset export complete: runs={manifest['run_count']} "
        f"events={manifest['event_count']} lessons={manifest['lesson_count']}"
    )
    typer.echo(f"Output directory: {output_dir}")


@app.command("run-scenario")
def run_scenario_command(
    scenario: Path = typer.Option(sample_scenario_path(), exists=True, resolve_path=True),
    blue_force: Path = typer.Option(sample_blue_force_path(), exists=True, resolve_path=True),
    red_force: Path = typer.Option(sample_red_force_path(), exists=True, resolve_path=True),
    blue_coa: Path = typer.Option(sample_blue_coa_a_path(), exists=True, resolve_path=True),
    red_coa: Path = typer.Option(sample_red_coa_path(), exists=True, resolve_path=True),
    seed: int = typer.Option(42, min=0),
    output_dir: Path = typer.Option(default_runs_dir(), resolve_path=True),
) -> None:
    try:
        scenario_obj, blue_force_obj, red_force_obj, blue_coas, red_coa_obj = _load_bundle(
            scenario,
            blue_force,
            red_force,
            [blue_coa],
            red_coa,
        )
    except SemanticValidationError as exc:
        _echo_validation_failure(exc)
        raise typer.Exit(code=1) from exc

    artifacts = run_scenario(
        scenario=scenario_obj,
        blue_force=blue_force_obj,
        red_force=red_force_obj,
        blue_coa=blue_coas[0],
        red_coa=red_coa_obj,
        seed=seed,
    )
    run_dir = persist_run_bundle(
        output_root=output_dir,
        manifest=artifacts.manifest,
        turn_states=artifacts.turn_states,
        event_logs=artifacts.event_logs,
        aar=artifacts.aar,
        lessons=artifacts.lessons,
    )

    blue_score = artifacts.manifest.summary_scores[Side.BLUE]
    red_score = artifacts.manifest.summary_scores[Side.RED]
    typer.echo(f"Run complete: {artifacts.manifest.id}")
    typer.echo(f"Output directory: {run_dir}")
    typer.echo(
        f"Final scores | blue={blue_score.overall_score:.3f} red={red_score.overall_score:.3f} "
        f"outcome={artifacts.manifest.final_outcome}"
    )


@app.command("run-runtime-demo")
def run_runtime_demo(
    scenario: Path = typer.Option(sample_scenario_path(), exists=True, resolve_path=True),
    blue_force: Path = typer.Option(sample_blue_force_path(), exists=True, resolve_path=True),
    red_force: Path = typer.Option(sample_red_force_path(), exists=True, resolve_path=True),
    blue_mode: PlannerMode = typer.Option(PlannerMode.HEURISTIC),
    red_mode: PlannerMode = typer.Option(PlannerMode.HEURISTIC),
    blue_coa: Path = typer.Option(sample_blue_coa_a_path(), exists=True, resolve_path=True),
    red_coa: Path = typer.Option(sample_red_coa_path(), exists=True, resolve_path=True),
    seed: int = typer.Option(42, min=0),
    output_dir: Path = typer.Option(default_runs_dir(), resolve_path=True),
) -> None:
    try:
        scenario_obj, blue_force_obj, red_force_obj = _load_runtime_assets(
            scenario,
            blue_force,
            red_force,
        )
        blue_planner = _build_runtime_planner(
            side=Side.BLUE,
            mode=blue_mode,
            scenario=scenario_obj,
            force_package=blue_force_obj,
            coa_path=blue_coa,
        )
        red_planner = _build_runtime_planner(
            side=Side.RED,
            mode=red_mode,
            scenario=scenario_obj,
            force_package=red_force_obj,
            coa_path=red_coa,
        )
    except SemanticValidationError as exc:
        _echo_validation_failure(exc)
        raise typer.Exit(code=1) from exc

    artifacts = run_scenario_with_planners(
        scenario=scenario_obj,
        blue_force=blue_force_obj,
        red_force=red_force_obj,
        blue_planner=blue_planner,
        red_planner=red_planner,
        seed=seed,
    )
    run_dir = persist_run_bundle(
        output_root=output_dir,
        manifest=artifacts.manifest,
        turn_states=artifacts.turn_states,
        event_logs=artifacts.event_logs,
        aar=artifacts.aar,
        lessons=artifacts.lessons,
    )

    blue_score = artifacts.manifest.summary_scores[Side.BLUE]
    red_score = artifacts.manifest.summary_scores[Side.RED]
    typer.echo(f"Runtime demo complete: {artifacts.manifest.id}")
    typer.echo(
        f"Planners | blue={artifacts.manifest.blue_coa_id} red={artifacts.manifest.red_coa_id}"
    )
    typer.echo(
        f"Final scores | blue={blue_score.overall_score:.3f} red={red_score.overall_score:.3f} "
        f"outcome={artifacts.manifest.final_outcome}"
    )
    typer.echo(f"Output directory: {run_dir}")


@app.command("compare-coas")
def compare_coas(
    scenario: Path = typer.Option(sample_scenario_path(), exists=True, resolve_path=True),
    blue_force: Path = typer.Option(sample_blue_force_path(), exists=True, resolve_path=True),
    red_force: Path = typer.Option(sample_red_force_path(), exists=True, resolve_path=True),
    blue_coa_a: Path = typer.Option(sample_blue_coa_a_path(), exists=True, resolve_path=True),
    blue_coa_b: Path = typer.Option(sample_blue_coa_b_path(), exists=True, resolve_path=True),
    red_coa: Path = typer.Option(sample_red_coa_path(), exists=True, resolve_path=True),
    seed: list[int] | None = typer.Option(None, min=0),
    output_dir: Path = typer.Option(default_runs_dir(), resolve_path=True),
) -> None:
    seed_list = seed or [11, 22, 33]
    try:
        scenario_obj, blue_force_obj, red_force_obj, blue_coas, red_coa_obj = _load_bundle(
            scenario,
            blue_force,
            red_force,
            [blue_coa_a, blue_coa_b],
            red_coa,
        )
    except SemanticValidationError as exc:
        _echo_validation_failure(exc)
        raise typer.Exit(code=1) from exc

    manifests_by_coa: dict[str, list] = {coa.id: [] for coa in blue_coas}
    run_dirs: list[Path] = []

    for blue_coa_obj in blue_coas:
        for item in seed_list:
            artifacts = run_scenario(
                scenario=scenario_obj,
                blue_force=blue_force_obj,
                red_force=red_force_obj,
                blue_coa=blue_coa_obj,
                red_coa=red_coa_obj,
                seed=item,
            )
            run_dir = persist_run_bundle(
                output_root=output_dir,
                manifest=artifacts.manifest,
                turn_states=artifacts.turn_states,
                event_logs=artifacts.event_logs,
                aar=artifacts.aar,
                lessons=artifacts.lessons,
            )
            run_dirs.append(run_dir)
            manifests_by_coa[blue_coa_obj.id].append(artifacts.manifest)

    comparison = aggregate_comparison(
        scenario=scenario_obj,
        manifests_by_coa=manifests_by_coa,
        red_coa_id=red_coa_obj.id,
        seed_list=seed_list,
    )
    comparison_dir = persist_comparison_bundle(output_dir, comparison, run_dirs)

    typer.echo(f"Comparison complete: {comparison.id}")
    typer.echo(f"Recommended blue COA: {comparison.recommended_coa}")
    typer.echo(
        f"Score delta={comparison.paired_seed_stats['score_delta']:.3f} "
        f"confidence={comparison.paired_seed_stats['confidence']:.3f}"
    )
    typer.echo(f"Output directory: {comparison_dir}")
