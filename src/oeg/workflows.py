from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from oeg.analysis.reporting import aggregate_comparison
from oeg.sampling import get_sampling_profile
from oeg.sampling import instantiate_bundle
from oeg.schemas.models import COAComparison
from oeg.schemas.models import COATemplate
from oeg.schemas.models import ForceTemplate
from oeg.schemas.models import Scenario
from oeg.schemas.models import ScenarioTemplate
from oeg.simulation.engine import run_scenario
from oeg.storage.catalog import load_approved_template_index
from oeg.storage.io import load_model
from oeg.storage.io import persist_comparison_bundle
from oeg.storage.io import persist_instantiated_assets
from oeg.storage.io import persist_run_bundle
from oeg.validation.semantic import SemanticValidationError
from oeg.validation.semantic import validate_coa_template_semantics
from oeg.validation.semantic import validate_force_template_semantics
from oeg.validation.semantic import validate_scenario_template_semantics


@dataclass
class TemplateBundle:
    scenario_template: ScenarioTemplate
    blue_force_template: ForceTemplate
    red_force_template: ForceTemplate
    blue_coa_templates: list[COATemplate]
    red_coa_template: COATemplate


@dataclass
class InstantiationWorkflowResult:
    bundle: object
    output_dir: Path


@dataclass
class BatchWorkflowResult:
    comparison: COAComparison
    comparison_dir: Path
    run_dirs: list[Path]
    scenario: Scenario


def load_template_bundle(
    scenario_template_path: Path,
    blue_force_template_path: Path,
    red_force_template_path: Path,
    blue_coa_template_paths: list[Path],
    red_coa_template_path: Path,
) -> TemplateBundle:
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

    return TemplateBundle(
        scenario_template=scenario_template,
        blue_force_template=blue_force_template,
        red_force_template=red_force_template,
        blue_coa_templates=blue_coa_templates,
        red_coa_template=red_coa_template,
    )


def enforce_template_approvals(
    *,
    catalog_path: Path,
    scenario_template: ScenarioTemplate,
    blue_force_template: ForceTemplate,
    red_force_template: ForceTemplate,
    blue_coa_templates: list[COATemplate],
    red_coa_template: COATemplate,
) -> None:
    approved = load_approved_template_index(catalog_path)
    required_templates = [
        ("scenario_template", scenario_template.id),
        ("force_template", blue_force_template.id),
        ("force_template", red_force_template.id),
        ("coa_template", red_coa_template.id),
        *[("coa_template", template.id) for template in blue_coa_templates],
    ]
    missing = [
        f"{template_kind}:{template_id}"
        for template_kind, template_id in required_templates
        if template_id not in approved.get(template_kind, set())
    ]
    if missing:
        raise ValueError(
            "Batch execution requires catalog-approved templates. "
            f"Missing approvals for {missing}. Rebuild the catalog or run with approvals disabled."
        )


def instantiate_template_assets(
    *,
    template_bundle: TemplateBundle,
    seed: int,
    sampling_profile: str,
    output_dir: Path,
) -> InstantiationWorkflowResult:
    profile = get_sampling_profile(sampling_profile)
    bundle = instantiate_bundle(
        scenario_template=template_bundle.scenario_template,
        blue_force_template=template_bundle.blue_force_template,
        red_force_template=template_bundle.red_force_template,
        blue_coa_template=template_bundle.blue_coa_templates[0],
        red_coa_template=template_bundle.red_coa_template,
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
    return InstantiationWorkflowResult(bundle=bundle, output_dir=instantiation_dir)


def run_batch_from_templates(
    *,
    template_bundle: TemplateBundle,
    seeds: list[int],
    sampling_profile: str,
    output_dir: Path,
    catalog_path: Path | None = None,
    require_approved: bool = True,
) -> BatchWorkflowResult:
    if require_approved:
        if catalog_path is None:
            raise ValueError("catalog_path is required when require_approved is true.")
        enforce_template_approvals(
            catalog_path=catalog_path,
            scenario_template=template_bundle.scenario_template,
            blue_force_template=template_bundle.blue_force_template,
            red_force_template=template_bundle.red_force_template,
            blue_coa_templates=template_bundle.blue_coa_templates,
            red_coa_template=template_bundle.red_coa_template,
        )

    profile = get_sampling_profile(sampling_profile)
    manifests_by_coa: dict[str, list] = {
        coa_template.base_coa.id: [] for coa_template in template_bundle.blue_coa_templates
    }
    run_dirs: list[Path] = []
    comparison_scenario: Scenario | None = None

    for blue_coa_template in template_bundle.blue_coa_templates:
        for seed in seeds:
            bundle = instantiate_bundle(
                scenario_template=template_bundle.scenario_template,
                blue_force_template=template_bundle.blue_force_template,
                red_force_template=template_bundle.red_force_template,
                blue_coa_template=blue_coa_template,
                red_coa_template=template_bundle.red_coa_template,
                seed=seed,
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
                seed=seed,
            )
            artifacts.manifest.instantiation_id = bundle.instantiation.id
            artifacts.manifest.stochastic_profile_id = profile.profile_id
            artifacts.manifest.source_scenario_template_id = template_bundle.scenario_template.id
            artifacts.manifest.source_blue_force_template_id = template_bundle.blue_force_template.id
            artifacts.manifest.source_red_force_template_id = template_bundle.red_force_template.id
            artifacts.manifest.source_blue_coa_template_id = blue_coa_template.id
            artifacts.manifest.source_red_coa_template_id = template_bundle.red_coa_template.id
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

    if comparison_scenario is None:
        raise ValueError("At least one seed is required to run a batch.")

    comparison = aggregate_comparison(
        scenario=comparison_scenario,
        manifests_by_coa=manifests_by_coa,
        red_coa_id=template_bundle.red_coa_template.base_coa.id,
        seed_list=seeds,
    )
    comparison_dir = persist_comparison_bundle(output_dir, comparison, run_dirs)
    return BatchWorkflowResult(
        comparison=comparison,
        comparison_dir=comparison_dir,
        run_dirs=run_dirs,
        scenario=comparison_scenario,
    )
