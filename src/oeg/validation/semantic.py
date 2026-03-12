from __future__ import annotations

from collections import defaultdict
from collections import deque

from oeg.schemas.models import ActionType
from oeg.schemas.models import COA
from oeg.schemas.models import COATemplate
from oeg.schemas.models import ForcePackage
from oeg.schemas.models import ForceTemplate
from oeg.schemas.models import Scenario
from oeg.schemas.models import ScenarioTemplate


ALLOWED_METRICS = {"objective_control", "force_preservation", "sustainment", "tempo"}


class SemanticValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def validate_scenario_semantics(scenario: Scenario) -> None:
    errors: list[str] = []
    zone_ids = [zone.id for zone in scenario.zones]
    zone_set = set(zone_ids)
    if len(zone_ids) != len(zone_set):
        errors.append("Scenario zones must have unique ids.")

    graph: dict[str, set[str]] = {zone_id: set() for zone_id in zone_ids}
    for edge in scenario.edges:
        if edge.a not in zone_set or edge.b not in zone_set:
            errors.append(f"Edge {edge.a}->{edge.b} references an unknown zone.")
            continue
        graph[edge.a].add(edge.b)
        graph[edge.b].add(edge.a)

    if zone_ids:
        visited: set[str] = set()
        queue: deque[str] = deque([zone_ids[0]])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            queue.extend(graph[current] - visited)
        if visited != zone_set:
            errors.append("Scenario zone graph must be fully connected.")

    for zone_id in scenario.initial_zone_control:
        if zone_id not in zone_set:
            errors.append(f"Initial zone control references unknown zone {zone_id}.")

    for objective in scenario.objectives:
        if objective.target_zone not in zone_set:
            errors.append(
                f"Objective {objective.id} references unknown zone {objective.target_zone}."
            )

    unknown_metrics = set(scenario.scoring_weights) - ALLOWED_METRICS
    if unknown_metrics:
        errors.append(f"Unknown scoring metric(s): {sorted(unknown_metrics)}")
    if sum(scenario.scoring_weights.values()) <= 0:
        errors.append("Scenario scoring weights must sum to a positive value.")

    if errors:
        raise SemanticValidationError(errors)


def validate_force_package_semantics(scenario: Scenario, force_package: ForcePackage) -> None:
    errors: list[str] = []
    zone_set = {zone.id for zone in scenario.zones}
    unit_ids = [unit.id for unit in force_package.units]
    if len(unit_ids) != len(set(unit_ids)):
        errors.append(f"Force package {force_package.id} contains duplicate unit ids.")

    for unit in force_package.units:
        if unit.location not in zone_set:
            errors.append(
                f"Unit {unit.id} in force package {force_package.id} is in unknown zone {unit.location}."
            )

    if errors:
        raise SemanticValidationError(errors)


def validate_coa_semantics(scenario: Scenario, force_package: ForcePackage, coa: COA) -> None:
    errors: list[str] = []
    zone_set = {zone.id for zone in scenario.zones}
    unit_ids = {unit.id for unit in force_package.units}
    orders_by_turn_unit: dict[tuple[int, str], list[ActionType]] = defaultdict(list)

    if coa.side != force_package.side:
        errors.append(
            f"COA {coa.id} side {coa.side.value} does not match force package side {force_package.side.value}."
        )

    for action in coa.actions:
        key = (action.turn, action.unit_id)
        orders_by_turn_unit[key].append(action.action)
        if action.turn > scenario.max_turns:
            errors.append(
                f"COA {coa.id} action for unit {action.unit_id} exceeds scenario max turns."
            )
        if action.unit_id not in unit_ids:
            errors.append(f"COA {coa.id} references unknown unit {action.unit_id}.")
        if action.target_zone and action.target_zone not in zone_set:
            errors.append(
                f"COA {coa.id} action for unit {action.unit_id} references unknown zone {action.target_zone}."
            )
        if action.action == ActionType.SUPPORT:
            invalid_support_targets = [item for item in action.support_unit_ids if item not in unit_ids]
            if invalid_support_targets:
                errors.append(
                    f"COA {coa.id} support action references unknown support units {invalid_support_targets}."
                )

    duplicate_orders = [
        f"turn {turn}, unit {unit_id}"
        for (turn, unit_id), actions in orders_by_turn_unit.items()
        if len(actions) > 1
    ]
    if duplicate_orders:
        errors.append(
            f"COA {coa.id} has multiple orders for the same unit/turn: {duplicate_orders}."
        )

    if errors:
        raise SemanticValidationError(errors)


def validate_asset_bundle(
    scenario: Scenario,
    blue_force: ForcePackage,
    red_force: ForcePackage,
    blue_coas: list[COA],
    red_coa: COA,
) -> None:
    errors: list[str] = []

    for validator, payload in (
        (validate_scenario_semantics, scenario),
        (validate_force_package_semantics, (scenario, blue_force)),
        (validate_force_package_semantics, (scenario, red_force)),
    ):
        try:
            if isinstance(payload, tuple):
                validator(*payload)
            else:
                validator(payload)
        except SemanticValidationError as exc:
            errors.extend(exc.errors)

    cross_force_ids = {unit.id for unit in blue_force.units} & {unit.id for unit in red_force.units}
    if cross_force_ids:
        errors.append(f"Blue and red force packages share unit ids: {sorted(cross_force_ids)}.")

    for coa, force_package in [(item, blue_force) for item in blue_coas] + [(red_coa, red_force)]:
        try:
            validate_coa_semantics(scenario, force_package, coa)
        except SemanticValidationError as exc:
            errors.extend(exc.errors)

    if errors:
        raise SemanticValidationError(errors)


def validate_scenario_template_semantics(template: ScenarioTemplate) -> None:
    errors: list[str] = []
    try:
        validate_scenario_semantics(template.base_scenario)
    except SemanticValidationError as exc:
        errors.extend(exc.errors)

    zone_ids = {zone.id for zone in template.base_scenario.zones}
    for zone_id in template.zone_strategic_value_adjustments:
        if zone_id not in zone_ids:
            errors.append(
                f"Scenario template {template.id} references unknown zone {zone_id} in strategic value adjustments."
            )

    if errors:
        raise SemanticValidationError(errors)


def validate_force_template_semantics(
    scenario_template: ScenarioTemplate,
    force_template: ForceTemplate,
) -> None:
    errors: list[str] = []
    scenario = scenario_template.base_scenario
    force_package = force_template.base_force

    try:
        validate_force_package_semantics(scenario, force_package)
    except SemanticValidationError as exc:
        errors.extend(exc.errors)

    if force_template.side != force_package.side:
        errors.append(
            f"Force template {force_template.id} side {force_template.side.value} does not match base force side {force_package.side.value}."
        )

    zone_ids = {zone.id for zone in scenario.zones}
    unit_ids = {unit.id for unit in force_package.units}
    for variation in force_template.unit_variability:
        if variation.unit_id not in unit_ids:
            errors.append(
                f"Force template {force_template.id} references unknown unit {variation.unit_id}."
            )
        invalid_locations = [
            option.value for option in variation.location_options if option.value not in zone_ids
        ]
        if invalid_locations:
            errors.append(
                f"Force template {force_template.id} unit {variation.unit_id} references unknown location options {invalid_locations}."
            )

    if errors:
        raise SemanticValidationError(errors)


def validate_coa_template_semantics(
    scenario_template: ScenarioTemplate,
    force_template: ForceTemplate,
    coa_template: COATemplate,
) -> None:
    errors: list[str] = []
    scenario = scenario_template.base_scenario
    force_package = force_template.base_force
    coa = coa_template.base_coa

    try:
        validate_coa_semantics(scenario, force_package, coa)
    except SemanticValidationError as exc:
        errors.extend(exc.errors)

    if coa_template.side != force_template.side:
        errors.append(
            f"COA template {coa_template.id} side {coa_template.side.value} does not match force template side {force_template.side.value}."
        )

    zone_ids = {zone.id for zone in scenario.zones}
    unit_ids = {unit.id for unit in force_package.units}
    action_keys = {(action.turn, action.unit_id) for action in coa.actions}
    seen_variations: set[tuple[int, str]] = set()
    for variation in coa_template.action_variations:
        key = (variation.turn, variation.unit_id)
        if key in seen_variations:
            errors.append(
                f"COA template {coa_template.id} has duplicate variation entries for turn {variation.turn}, unit {variation.unit_id}."
            )
        seen_variations.add(key)

        if variation.turn > scenario.max_turns:
            errors.append(
                f"COA template {coa_template.id} variation for unit {variation.unit_id} exceeds scenario max turns."
            )
        if variation.unit_id not in unit_ids:
            errors.append(
                f"COA template {coa_template.id} references unknown unit {variation.unit_id}."
            )
        if key not in action_keys:
            errors.append(
                f"COA template {coa_template.id} variation for turn {variation.turn}, unit {variation.unit_id} does not match a base COA action."
            )
        for option in variation.options:
            if option.target_zone and option.target_zone not in zone_ids:
                errors.append(
                    f"COA template {coa_template.id} option for unit {variation.unit_id} references unknown zone {option.target_zone}."
                )
            invalid_support_targets = [
                item for item in option.support_unit_ids if item not in unit_ids
            ]
            if invalid_support_targets:
                errors.append(
                    f"COA template {coa_template.id} option for unit {variation.unit_id} references unknown support units {invalid_support_targets}."
                )

    if errors:
        raise SemanticValidationError(errors)
