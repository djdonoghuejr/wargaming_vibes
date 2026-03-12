from __future__ import annotations

from oeg.paths import sample_blue_coa_template_a_path
from oeg.paths import sample_blue_force_template_path
from oeg.paths import sample_red_coa_template_path
from oeg.paths import sample_red_force_template_path
from oeg.paths import sample_scenario_template_path
from oeg.sampling import get_sampling_profile
from oeg.sampling import instantiate_bundle
from oeg.storage.io import load_model
from oeg.schemas.models import COATemplate
from oeg.schemas.models import ForceTemplate
from oeg.schemas.models import ScenarioTemplate


def _load_templates():
    return (
        load_model(sample_scenario_template_path(), ScenarioTemplate),
        load_model(sample_blue_force_template_path(), ForceTemplate),
        load_model(sample_red_force_template_path(), ForceTemplate),
        load_model(sample_blue_coa_template_a_path(), COATemplate),
        load_model(sample_red_coa_template_path(), COATemplate),
    )


def test_instantiate_bundle_is_seed_replayable() -> None:
    scenario_template, blue_force_template, red_force_template, blue_coa_template, red_coa_template = _load_templates()
    profile = get_sampling_profile("hybrid_stochastic_v1")

    bundle_a = instantiate_bundle(
        scenario_template,
        blue_force_template,
        red_force_template,
        blue_coa_template,
        red_coa_template,
        seed=17,
        profile=profile,
    )
    bundle_b = instantiate_bundle(
        scenario_template,
        blue_force_template,
        red_force_template,
        blue_coa_template,
        red_coa_template,
        seed=17,
        profile=profile,
    )

    assert bundle_a.instantiation.sampled_values == bundle_b.instantiation.sampled_values
    assert bundle_a.scenario.environment.weather == bundle_b.scenario.environment.weather
    assert bundle_a.blue_force.units[0].readiness == bundle_b.blue_force.units[0].readiness
    assert bundle_a.blue_coa.actions == bundle_b.blue_coa.actions


def test_instantiate_bundle_changes_with_seed() -> None:
    scenario_template, blue_force_template, red_force_template, blue_coa_template, red_coa_template = _load_templates()
    profile = get_sampling_profile("hybrid_stochastic_v1")

    bundle_a = instantiate_bundle(
        scenario_template,
        blue_force_template,
        red_force_template,
        blue_coa_template,
        red_coa_template,
        seed=11,
        profile=profile,
    )
    bundle_b = instantiate_bundle(
        scenario_template,
        blue_force_template,
        red_force_template,
        blue_coa_template,
        red_coa_template,
        seed=22,
        profile=profile,
    )

    assert bundle_a.instantiation.sampled_values != bundle_b.instantiation.sampled_values
