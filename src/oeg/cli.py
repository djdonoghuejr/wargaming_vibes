from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

import typer

from oeg.analysis.lessons import aggregate_lessons
from oeg.analysis.reporting import aggregate_comparison
from oeg.evaluation.quality import evaluate_runs
from oeg.evaluation.quality import evaluate_templates
from oeg.paths import default_analysis_dir
from oeg.paths import default_catalog_path
from oeg.paths import template_dir
from oeg.generators import FileReplayGenerationProvider
from oeg.generators import GenerationRequest
from oeg.generators import OfflineGenerationPipeline
from oeg.generators import OpenAIResponsesGenerationProvider
from oeg.paths import default_datasets_dir
from oeg.paths import default_generated_dir
from oeg.paths import default_runs_dir
from oeg.paths import sample_blue_coa_a_path
from oeg.paths import sample_blue_coa_template_a_path
from oeg.paths import sample_blue_coa_template_b_path
from oeg.paths import sample_blue_coa_b_path
from oeg.paths import sample_blue_force_path
from oeg.paths import sample_blue_force_template_path
from oeg.paths import sample_red_coa_template_path
from oeg.paths import sample_red_coa_path
from oeg.paths import sample_red_force_path
from oeg.paths import sample_red_force_template_path
from oeg.paths import sample_scenario_path
from oeg.paths import sample_scenario_template_path
from oeg.planners import COAPlanner
from oeg.planners import HeuristicPlanner
from oeg.planners import Planner
from oeg.sampling import get_sampling_profile
from oeg.sampling import instantiate_bundle
from oeg.schemas.models import COA
from oeg.schemas.models import COATemplate
from oeg.schemas.models import ForcePackage
from oeg.schemas.models import ForceTemplate
from oeg.schemas.models import Scenario
from oeg.schemas.models import ScenarioTemplate
from oeg.schemas.models import Side
from oeg.simulation.engine import run_scenario
from oeg.simulation.engine import run_scenario_with_planners
from oeg.storage.io import load_model
from oeg.storage.io import persist_comparison_bundle
from oeg.storage.io import persist_instantiated_assets
from oeg.storage.io import persist_run_bundle
from oeg.storage.catalog import build_duckdb_catalog
from oeg.storage.export import export_run_dataset
from oeg.validation.semantic import SemanticValidationError
from oeg.validation.semantic import validate_asset_bundle
from oeg.validation.semantic import validate_coa_semantics
from oeg.validation.semantic import validate_coa_template_semantics
from oeg.validation.semantic import validate_force_package_semantics
from oeg.validation.semantic import validate_force_template_semantics
from oeg.validation.semantic import validate_scenario_semantics
from oeg.validation.semantic import validate_scenario_template_semantics


app = typer.Typer(help="Operational Experiment Generator CLI")


class PlannerMode(str, Enum):
    HEURISTIC = "heuristic"
    COA = "coa"


class ReasoningEffort(str, Enum):
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def _default_blue_coas() -> list[Path]:
    return [sample_blue_coa_a_path(), sample_blue_coa_b_path()]


def _default_blue_coa_templates() -> list[Path]:
    return [sample_blue_coa_template_a_path(), sample_blue_coa_template_b_path()]


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


def _load_template_bundle(
    scenario_template_path: Path,
    blue_force_template_path: Path,
    red_force_template_path: Path,
    blue_coa_template_paths: list[Path],
    red_coa_template_path: Path,
) -> tuple[ScenarioTemplate, ForceTemplate, ForceTemplate, list[COATemplate], COATemplate]:
    scenario_template = load_model(scenario_template_path, ScenarioTemplate)
    blue_force_template = load_model(blue_force_template_path, ForceTemplate)
    red_force_template = load_model(red_force_template_path, ForceTemplate)
    blue_coa_templates = [load_model(path, COATemplate) for path in blue_coa_template_paths]
    red_coa_template = load_model(red_coa_template_path, COATemplate)

    errors: list[str] = []
    try:
        validate_scenario_template_semantics(scenario_template)
    except SemanticValidationError as exc:
        errors.extend(exc.errors)

    for force_template in (blue_force_template, red_force_template):
        try:
            validate_force_template_semantics(scenario_template, force_template)
        except SemanticValidationError as exc:
            errors.extend(exc.errors)

    for coa_template, force_template in (
        *[(item, blue_force_template) for item in blue_coa_templates],
        (red_coa_template, red_force_template),
    ):
        try:
            validate_coa_template_semantics(scenario_template, force_template, coa_template)
        except SemanticValidationError as exc:
            errors.extend(exc.errors)

    if errors:
        raise SemanticValidationError(errors)

    return (
        scenario_template,
        blue_force_template,
        red_force_template,
        blue_coa_templates,
        red_coa_template,
    )


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


@app.command("generate-live-batch")
def generate_live_batch(
    request_file: Path = typer.Option(..., exists=True, resolve_path=True),
    output_dir: Path = typer.Option(default_generated_dir(), resolve_path=True),
    model: str = typer.Option("gpt-5-mini"),
    api_key: str | None = typer.Option(
        None,
        envvar="OPENAI_API_KEY",
        help="OpenAI API key. Defaults to OPENAI_API_KEY if present.",
    ),
    temperature: float | None = typer.Option(None, min=0.0, max=2.0),
    max_output_tokens: int | None = typer.Option(4000, min=1),
    reasoning_effort: ReasoningEffort | None = typer.Option(None),
) -> None:
    try:
        requests = _load_generation_requests(request_file)
        provider = OpenAIResponsesGenerationProvider(
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort.value if reasoning_effort else None,
        )
        pipeline = OfflineGenerationPipeline(output_dir)
        result = pipeline.run_batch(requests, provider)
    except (RuntimeError, ValueError, SemanticValidationError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"Live generation batch complete: {result.batch_id}")
    typer.echo(
        f"Promoted={result.promoted_count} quarantined={result.quarantined_count}"
    )
    typer.echo(f"Output directory: {output_dir / result.batch_id}")


@app.command("instantiate-assets")
def instantiate_assets(
    scenario_template: Path = typer.Option(sample_scenario_template_path(), exists=True, resolve_path=True),
    blue_force_template: Path = typer.Option(sample_blue_force_template_path(), exists=True, resolve_path=True),
    red_force_template: Path = typer.Option(sample_red_force_template_path(), exists=True, resolve_path=True),
    blue_coa_template: Path = typer.Option(sample_blue_coa_template_a_path(), exists=True, resolve_path=True),
    red_coa_template: Path = typer.Option(sample_red_coa_template_path(), exists=True, resolve_path=True),
    seed: int = typer.Option(42, min=0),
    sampling_profile: str = typer.Option("hybrid_stochastic_v1"),
    output_dir: Path = typer.Option(default_generated_dir(), resolve_path=True),
) -> None:
    try:
        (
            scenario_template_obj,
            blue_force_template_obj,
            red_force_template_obj,
            blue_coa_templates,
            red_coa_template_obj,
        ) = _load_template_bundle(
            scenario_template,
            blue_force_template,
            red_force_template,
            [blue_coa_template],
            red_coa_template,
        )
        profile = get_sampling_profile(sampling_profile)
        bundle = instantiate_bundle(
            scenario_template=scenario_template_obj,
            blue_force_template=blue_force_template_obj,
            red_force_template=red_force_template_obj,
            blue_coa_template=blue_coa_templates[0],
            red_coa_template=red_coa_template_obj,
            seed=seed,
            profile=profile,
        )
        instantiation_dir = persist_instantiated_assets(
            output_root=output_dir,
            instantiation=bundle.instantiation,
            scenario=bundle.scenario,
            blue_force=bundle.blue_force,
            red_force=bundle.red_force,
            blue_coa=bundle.blue_coa,
            red_coa=bundle.red_coa,
        )
    except (KeyError, SemanticValidationError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"Instantiation complete: {bundle.instantiation.id}")
    typer.echo(f"Sampling profile: {profile.profile_id}")
    typer.echo(f"Output directory: {instantiation_dir}")


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


@app.command("aggregate-lessons")
def aggregate_lessons_command(
    runs_dir: Path = typer.Option(default_runs_dir(), exists=True, resolve_path=True),
    output_dir: Path = typer.Option(default_analysis_dir(), resolve_path=True),
) -> None:
    manifest = aggregate_lessons(runs_dir, output_dir)
    typer.echo(
        f"Lesson aggregation complete: runs={manifest['run_count']} "
        f"lessons={manifest['lesson_count']} clusters={manifest['cluster_count']}"
    )
    typer.echo(f"Output directory: {output_dir}")


@app.command("evaluate-runs")
def evaluate_runs_command(
    runs_dir: Path = typer.Option(default_runs_dir(), exists=True, resolve_path=True),
    output_dir: Path = typer.Option(default_analysis_dir(), resolve_path=True),
) -> None:
    manifest = evaluate_runs(runs_dir, output_dir)
    typer.echo(
        f"Run evaluation complete: runs={manifest['run_count']} "
        f"pass={manifest['pass_count']} warnings={manifest['warning_count']} weak={manifest['fail_count']}"
    )
    typer.echo(f"Output directory: {output_dir}")


@app.command("evaluate-templates")
def evaluate_templates_command(
    templates_dir: Path = typer.Option(template_dir(), exists=True, resolve_path=True),
    output_dir: Path = typer.Option(default_analysis_dir(), resolve_path=True),
) -> None:
    manifest = evaluate_templates(templates_dir, output_dir)
    typer.echo(
        f"Template evaluation complete: templates={manifest['template_count']} "
        f"approved={manifest['approved_for_batch_count']} promoted={manifest['promoted_count']} "
        f"quarantined={manifest['quarantined_count']}"
    )
    typer.echo(f"Output directory: {output_dir}")


@app.command("build-catalog")
def build_catalog_command(
    runs_dir: Path = typer.Option(default_runs_dir(), exists=True, resolve_path=True),
    templates_dir: Path = typer.Option(template_dir(), exists=True, resolve_path=True),
    datasets_dir: Path = typer.Option(default_datasets_dir(), resolve_path=True),
    analysis_dir: Path = typer.Option(default_analysis_dir(), resolve_path=True),
    output_path: Path = typer.Option(default_catalog_path(), resolve_path=True),
) -> None:
    manifest = build_duckdb_catalog(
        runs_dir=runs_dir,
        templates_dir=templates_dir,
        datasets_dir=datasets_dir,
        analysis_dir=analysis_dir,
        output_path=output_path,
    )
    table_counts = manifest["table_counts"]
    typer.echo(
        f"DuckDB catalog complete: templates={table_counts['templates']} "
        f"runs={table_counts['run_manifests']} comparisons={table_counts['comparisons']}"
    )
    typer.echo(f"Catalog path: {output_path}")


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


@app.command("run-batch")
def run_batch(
    scenario_template: Path = typer.Option(sample_scenario_template_path(), exists=True, resolve_path=True),
    blue_force_template: Path = typer.Option(sample_blue_force_template_path(), exists=True, resolve_path=True),
    red_force_template: Path = typer.Option(sample_red_force_template_path(), exists=True, resolve_path=True),
    blue_coa_template: list[Path] | None = typer.Option(None, exists=True, resolve_path=True),
    red_coa_template: Path = typer.Option(sample_red_coa_template_path(), exists=True, resolve_path=True),
    seed: list[int] | None = typer.Option(None, min=0),
    sampling_profile: str = typer.Option("hybrid_stochastic_v1"),
    output_dir: Path = typer.Option(default_runs_dir(), resolve_path=True),
) -> None:
    seed_list = seed or [11, 22, 33]
    blue_coa_template_paths = blue_coa_template or _default_blue_coa_templates()

    try:
        (
            scenario_template_obj,
            blue_force_template_obj,
            red_force_template_obj,
            blue_coa_templates,
            red_coa_template_obj,
        ) = _load_template_bundle(
            scenario_template,
            blue_force_template,
            red_force_template,
            blue_coa_template_paths,
            red_coa_template,
        )
        profile = get_sampling_profile(sampling_profile)
    except (KeyError, SemanticValidationError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    manifests_by_coa: dict[str, list] = {coa_template.base_coa.id: [] for coa_template in blue_coa_templates}
    run_dirs: list[Path] = []
    comparison_scenario: Scenario | None = None

    for blue_coa_template_obj in blue_coa_templates:
        for item in seed_list:
            bundle = instantiate_bundle(
                scenario_template=scenario_template_obj,
                blue_force_template=blue_force_template_obj,
                red_force_template=red_force_template_obj,
                blue_coa_template=blue_coa_template_obj,
                red_coa_template=red_coa_template_obj,
                seed=item,
                profile=profile,
            )
            if comparison_scenario is None:
                comparison_scenario = bundle.scenario

            artifacts = run_scenario(
                scenario=bundle.scenario,
                blue_force=bundle.blue_force,
                red_force=bundle.red_force,
                blue_coa=bundle.blue_coa,
                red_coa=bundle.red_coa,
                seed=item,
            )
            artifacts.manifest.instantiation_id = bundle.instantiation.id
            artifacts.manifest.stochastic_profile_id = profile.profile_id
            artifacts.manifest.source_scenario_template_id = scenario_template_obj.id
            artifacts.manifest.source_blue_force_template_id = blue_force_template_obj.id
            artifacts.manifest.source_red_force_template_id = red_force_template_obj.id
            artifacts.manifest.source_blue_coa_template_id = blue_coa_template_obj.id
            artifacts.manifest.source_red_coa_template_id = red_coa_template_obj.id
            run_dir = persist_run_bundle(
                output_root=output_dir,
                manifest=artifacts.manifest,
                turn_states=artifacts.turn_states,
                event_logs=artifacts.event_logs,
                aar=artifacts.aar,
                lessons=artifacts.lessons,
                instantiation=bundle.instantiation,
            )
            run_dirs.append(run_dir)
            manifests_by_coa[bundle.blue_coa.id].append(artifacts.manifest)

    assert comparison_scenario is not None
    comparison = aggregate_comparison(
        scenario=comparison_scenario,
        manifests_by_coa=manifests_by_coa,
        red_coa_id=red_coa_template_obj.base_coa.id,
        seed_list=seed_list,
    )
    comparison_dir = persist_comparison_bundle(output_dir, comparison, run_dirs)

    typer.echo(f"Batch execution complete: {comparison.id}")
    typer.echo(f"Sampling profile: {profile.profile_id}")
    typer.echo(f"Recommended blue COA: {comparison.recommended_coa}")
    typer.echo(
        f"Score delta={comparison.paired_seed_stats['score_delta']:.3f} "
        f"confidence={comparison.paired_seed_stats['confidence']:.3f}"
    )
    typer.echo(f"Output directory: {comparison_dir}")
