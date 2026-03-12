from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from random import Random

from oeg.schemas.models import COA
from oeg.schemas.models import COATemplate
from oeg.schemas.models import ForcePackage
from oeg.schemas.models import ForceTemplate
from oeg.schemas.models import NumericRange
from oeg.schemas.models import RunInstantiation
from oeg.schemas.models import Scenario
from oeg.schemas.models import ScenarioTemplate
from oeg.storage.io import timestamp_id
from oeg.storage.io import utc_now_iso
from oeg.sampling.profiles import SamplingProfile


@dataclass
class InstantiatedBundle:
    scenario: Scenario
    blue_force: ForcePackage
    red_force: ForcePackage
    blue_coa: COA
    red_coa: COA
    instantiation: RunInstantiation


def instantiate_bundle(
    scenario_template: ScenarioTemplate,
    blue_force_template: ForceTemplate,
    red_force_template: ForceTemplate,
    blue_coa_template: COATemplate,
    red_coa_template: COATemplate,
    seed: int,
    profile: SamplingProfile,
) -> InstantiatedBundle:
    created_at = utc_now_iso()
    scenario_seed = _derive_seed(seed, f"scenario:{scenario_template.id}")
    blue_force_seed = _derive_seed(seed, f"force:{blue_force_template.id}")
    red_force_seed = _derive_seed(seed, f"force:{red_force_template.id}")
    blue_coa_seed = _derive_seed(seed, f"coa:{blue_coa_template.id}")
    red_coa_seed = _derive_seed(seed, f"coa:{red_coa_template.id}")

    scenario, scenario_samples = instantiate_scenario(
        scenario_template,
        scenario_seed,
        profile,
        created_at,
    )
    blue_force, blue_force_samples = instantiate_force(
        blue_force_template,
        blue_force_seed,
        profile,
        created_at,
    )
    red_force, red_force_samples = instantiate_force(
        red_force_template,
        red_force_seed,
        profile,
        created_at,
    )
    blue_coa, blue_coa_samples = instantiate_coa(
        blue_coa_template,
        blue_coa_seed,
        profile,
        created_at,
    )
    red_coa, red_coa_samples = instantiate_coa(
        red_coa_template,
        red_coa_seed,
        profile,
        created_at,
    )

    instantiation = RunInstantiation(
        id=timestamp_id(f"instantiation_{blue_coa_template.base_coa.id}_{seed}"),
        created_at=created_at,
        seed=seed,
        stochastic_profile_id=profile.profile_id,
        scenario_template_id=scenario_template.id,
        blue_force_template_id=blue_force_template.id,
        red_force_template_id=red_force_template.id,
        blue_coa_template_id=blue_coa_template.id,
        red_coa_template_id=red_coa_template.id,
        scenario_id=scenario.id,
        blue_force_package_id=blue_force.id,
        red_force_package_id=red_force.id,
        blue_coa_id=blue_coa.id,
        red_coa_id=red_coa.id,
        sampled_values={
            "component_seeds": {
                "scenario": scenario_seed,
                "blue_force": blue_force_seed,
                "red_force": red_force_seed,
                "blue_coa": blue_coa_seed,
                "red_coa": red_coa_seed,
            },
            "scenario": scenario_samples,
            "blue_force": blue_force_samples,
            "red_force": red_force_samples,
            "blue_coa": blue_coa_samples,
            "red_coa": red_coa_samples,
        },
    )
    return InstantiatedBundle(
        scenario=scenario,
        blue_force=blue_force,
        red_force=red_force,
        blue_coa=blue_coa,
        red_coa=red_coa,
        instantiation=instantiation,
    )


def instantiate_scenario(
    template: ScenarioTemplate,
    seed: int,
    profile: SamplingProfile,
    created_at: str | None = None,
) -> tuple[Scenario, dict[str, object]]:
    rng = Random(seed)
    scenario = template.base_scenario.model_copy(deep=True)
    scenario.created_at = created_at
    scenario.provenance = {
        **scenario.provenance,
        "scenario_template_id": template.id,
        "sampling_profile_id": profile.profile_id,
        "component_seed": seed,
    }

    sampled: dict[str, object] = {}
    if template.weather_options:
        scenario.environment.weather = _sample_weighted(
            template.weather_options,
            rng,
            profile.scenario_variation_scale,
        )
        sampled["weather"] = scenario.environment.weather
    if template.visibility_options:
        scenario.environment.visibility = _sample_weighted(
            template.visibility_options,
            rng,
            profile.scenario_variation_scale,
        )
        sampled["visibility"] = scenario.environment.visibility

    zone_adjustments: dict[str, int] = {}
    for zone in scenario.zones:
        range_value = template.zone_strategic_value_adjustments.get(zone.id)
        if not range_value:
            continue
        zone.strategic_value = int(
            round(
                _sample_range(
                    range_value,
                    rng,
                    profile.scenario_variation_scale,
                )
            )
        )
        zone.strategic_value = max(1, min(10, zone.strategic_value))
        zone_adjustments[zone.id] = zone.strategic_value
    if zone_adjustments:
        sampled["zone_strategic_values"] = zone_adjustments

    return scenario, sampled


def instantiate_force(
    template: ForceTemplate,
    seed: int,
    profile: SamplingProfile,
    created_at: str | None = None,
) -> tuple[ForcePackage, dict[str, object]]:
    rng = Random(seed)
    force = template.base_force.model_copy(deep=True)
    force.created_at = created_at
    force.provenance = {
        **force.provenance,
        "force_template_id": template.id,
        "sampling_profile_id": profile.profile_id,
        "component_seed": seed,
    }
    variation_by_unit = {variation.unit_id: variation for variation in template.unit_variability}
    sampled_units: dict[str, dict[str, object]] = {}
    for unit in force.units:
        variation = variation_by_unit.get(unit.id)
        if variation is None:
            continue

        sampled_unit: dict[str, object] = {}
        for field_name in ("readiness", "morale", "supply", "signature", "strength", "fatigue"):
            range_value = getattr(variation, field_name)
            if range_value is None:
                continue
            sampled_value = round(
                _sample_range(range_value, rng, profile.force_variation_scale),
                4,
            )
            setattr(unit, field_name, _clamp_01(sampled_value))
            sampled_unit[field_name] = getattr(unit, field_name)

        if variation.location_options:
            unit.location = _sample_weighted(
                variation.location_options,
                rng,
                profile.force_variation_scale,
            )
            sampled_unit["location"] = unit.location

        if sampled_unit:
            sampled_units[unit.id] = sampled_unit

    return force, {"units": sampled_units}


def instantiate_coa(
    template: COATemplate,
    seed: int,
    profile: SamplingProfile,
    created_at: str | None = None,
) -> tuple[COA, dict[str, object]]:
    rng = Random(seed)
    coa = template.base_coa.model_copy(deep=True)
    coa.created_at = created_at
    coa.provenance = {
        **coa.provenance,
        "coa_template_id": template.id,
        "sampling_profile_id": profile.profile_id,
        "component_seed": seed,
    }

    sampled_variations: dict[str, dict[str, object]] = {}
    actions_by_key = {(action.turn, action.unit_id): action for action in coa.actions}
    for variation in template.action_variations:
        selected = _sample_weighted(
            variation.options,
            rng,
            profile.coa_variation_scale,
        )
        action = actions_by_key[(variation.turn, variation.unit_id)]
        action.action = selected.action
        action.target_zone = selected.target_zone
        action.support_unit_ids = list(selected.support_unit_ids)
        action.notes = selected.notes or action.notes
        sampled_variations[f"turn_{variation.turn}_{variation.unit_id}"] = {
            "action": action.action.value,
            "target_zone": action.target_zone,
            "support_unit_ids": action.support_unit_ids,
            "notes": action.notes,
        }

    return coa, {"action_variations": sampled_variations}


def _sample_range(range_value: NumericRange, rng: Random, scale: float) -> float:
    midpoint = (range_value.min_value + range_value.max_value) / 2
    if scale <= 0:
        return midpoint
    raw_value = rng.uniform(range_value.min_value, range_value.max_value)
    return midpoint + ((raw_value - midpoint) * min(1.0, scale))


def _sample_weighted(options, rng: Random, scale: float):
    if scale <= 0:
        return max(options, key=lambda item: (item.weight, str(item.value))).value if hasattr(options[0], "value") else max(options, key=lambda item: (item.weight, str(item.action.value)))

    weighted_values: list[tuple[float, object]] = []
    running_total = 0.0
    for option in options:
        running_total += option.weight
        weighted_values.append((running_total, option))

    roll = rng.uniform(0.0, running_total)
    for threshold, option in weighted_values:
        if roll <= threshold:
            return option.value if hasattr(option, "value") else option
    option = weighted_values[-1][1]
    return option.value if hasattr(option, "value") else option


def _derive_seed(seed: int, label: str) -> int:
    digest = sha256(f"{seed}:{label}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def _clamp_01(value: float) -> float:
    return max(0.0, min(1.0, value))
