from __future__ import annotations

from dataclasses import dataclass
from random import Random

from oeg.analysis.reporting import build_aar
from oeg.analysis.reporting import extract_lessons
from oeg.schemas.models import AAR
from oeg.schemas.models import ActionType
from oeg.schemas.models import AdjudicationResult
from oeg.schemas.models import COA
from oeg.schemas.models import ControlState
from oeg.schemas.models import EventLog
from oeg.schemas.models import EventVisibility
from oeg.schemas.models import ForcePackage
from oeg.schemas.models import IssuedOrder
from oeg.schemas.models import LessonLearned
from oeg.schemas.models import Phase
from oeg.schemas.models import RunManifest
from oeg.schemas.models import Scenario
from oeg.schemas.models import Side
from oeg.schemas.models import SideObservation
from oeg.schemas.models import SideScore
from oeg.schemas.models import TruthState
from oeg.schemas.models import TurnState
from oeg.schemas.models import UnitState
from oeg.storage.io import timestamp_id
from oeg.storage.io import utc_now_iso


TEMPO_ACTIONS = {ActionType.MOVE, ActionType.ATTACK, ActionType.RECON, ActionType.SUPPORT}
TERRAIN_DEFENSE_BONUS = {
    "urban": 0.18,
    "open": 0.0,
    "elevated_open": 0.08,
    "industrial": 0.1,
    "airfield": 0.05,
}


@dataclass
class SimulationArtifacts:
    manifest: RunManifest
    turn_states: list[TurnState]
    event_logs: list[EventLog]
    aar: AAR
    lessons: list[LessonLearned]


def run_scenario(
    scenario: Scenario,
    blue_force: ForcePackage,
    red_force: ForcePackage,
    blue_coa: COA,
    red_coa: COA,
    seed: int,
) -> SimulationArtifacts:
    rng = Random(seed)
    run_id = timestamp_id(f"run_{scenario.id}_{blue_coa.id}_{seed}")
    created_at = utc_now_iso()

    unit_states = _initialize_units(blue_force, red_force)
    zone_control = _initialize_zone_control(scenario)
    observations = _initialize_observations()
    force_unit_count = {
        Side.BLUE: len(blue_force.units),
        Side.RED: len(red_force.units),
    }
    tempo_counts = {Side.BLUE: 0, Side.RED: 0}

    turn_states: list[TurnState] = []
    event_logs: list[EventLog] = []

    for turn in range(1, scenario.max_turns + 1):
        _age_observations(observations)
        orders = _build_orders_for_turn(turn, blue_force, red_force, blue_coa, red_coa)
        orders_by_unit = {order.unit_id: order for order in orders}

        turn_events: list[EventLog] = []
        turn_events.extend(_process_recon(turn, run_id, unit_states, observations, orders, rng))
        _apply_passive_detection(scenario, unit_states, observations)
        turn_events.extend(_process_movement(turn, run_id, scenario, unit_states, orders))
        support_bonus, support_events = _process_support(turn, run_id, unit_states, orders)
        turn_events.extend(support_events)
        turn_events.extend(_process_resupply(turn, run_id, unit_states, orders))
        turn_events.extend(
            _process_attacks(
                turn=turn,
                run_id=run_id,
                scenario=scenario,
                unit_states=unit_states,
                zone_control=zone_control,
                observations=observations,
                orders_by_unit=orders_by_unit,
                support_bonus=support_bonus,
                rng=rng,
            )
        )

        for event in turn_events:
            if event.adjudication.feasible and event.action_type in TEMPO_ACTIONS:
                tempo_counts[event.actor_side] += 1

        zone_control = _recompute_zone_control(scenario, zone_control, unit_states)
        side_views = _build_side_views(observations)
        scoreboard = _compute_scoreboard(
            scenario=scenario,
            unit_states=unit_states,
            zone_control=zone_control,
            tempo_counts=tempo_counts,
            force_unit_count=force_unit_count,
            current_turn=turn,
        )
        turn_state = TurnState(
            id=f"{run_id}_turn_{turn:02d}",
            created_at=created_at,
            source_run_id=run_id,
            run_id=run_id,
            turn_number=turn,
            phase=Phase.COMPLETED,
            rng_seed=seed,
            truth_state=TruthState(zone_control=zone_control, unit_status=unit_states),
            side_views=side_views,
            scoreboard=scoreboard,
            active_orders=orders,
        )
        turn_states.append(turn_state)
        event_logs.extend(turn_events)

    final_scores = turn_states[-1].scoreboard
    outcome = _mission_outcome(final_scores[Side.BLUE], final_scores[Side.RED])
    manifest = RunManifest(
        id=run_id,
        created_at=created_at,
        scenario_id=scenario.id,
        blue_force_package_id=blue_force.id,
        red_force_package_id=red_force.id,
        blue_coa_id=blue_coa.id,
        red_coa_id=red_coa.id,
        seed=seed,
        turns_completed=len(turn_states),
        summary_scores=final_scores,
        final_outcome=outcome,
    )
    lessons = extract_lessons(event_logs, run_id)
    aar = build_aar(scenario, manifest, event_logs, lessons)
    return SimulationArtifacts(manifest=manifest, turn_states=turn_states, event_logs=event_logs, aar=aar, lessons=lessons)


def _mission_outcome(blue_score: SideScore, red_score: SideScore) -> str:
    delta = blue_score.overall_score - red_score.overall_score
    if delta >= 0.1:
        return "blue_success"
    if delta >= 0.03:
        return "blue_marginal_success"
    if delta <= -0.1:
        return "red_success"
    if delta <= -0.03:
        return "red_marginal_success"
    return "draw"


def _initialize_zone_control(scenario: Scenario) -> dict[str, ControlState]:
    zone_control = {zone.id: ControlState.NEUTRAL for zone in scenario.zones}
    zone_control.update(scenario.initial_zone_control)
    return zone_control


def _initialize_units(
    blue_force: ForcePackage,
    red_force: ForcePackage,
) -> dict[str, UnitState]:
    unit_states: dict[str, UnitState] = {}
    for force in (blue_force, red_force):
        for unit in force.units:
            unit_states[unit.id] = UnitState(
                unit_id=unit.id,
                side=force.side,
                label=unit.label,
                location=unit.location,
                strength=unit.strength,
                readiness=unit.readiness,
                morale=unit.morale,
                supply=unit.supply,
                fatigue=unit.fatigue,
                signature=unit.signature,
                capabilities=unit.capabilities,
                destroyed=False,
            )
    return unit_states


def _initialize_observations() -> dict[Side, dict[str, dict[str, float | int | str]]]:
    return {Side.BLUE: {}, Side.RED: {}}


def _age_observations(observations: dict[Side, dict[str, dict[str, float | int | str]]]) -> None:
    for side_observations in observations.values():
        stale_units: list[str] = []
        for unit_id, contact in side_observations.items():
            contact["age"] = int(contact["age"]) + 1
            contact["confidence"] = round(float(contact["confidence"]) * 0.9, 4)
            if float(contact["confidence"]) < 0.15 and int(contact["age"]) > 3:
                stale_units.append(unit_id)
        for unit_id in stale_units:
            side_observations.pop(unit_id, None)


def _adjacency_map(scenario: Scenario) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {zone.id: set() for zone in scenario.zones}
    for edge in scenario.edges:
        adjacency[edge.a].add(edge.b)
        adjacency[edge.b].add(edge.a)
    return adjacency


def _build_orders_for_turn(
    turn: int,
    blue_force: ForcePackage,
    red_force: ForcePackage,
    blue_coa: COA,
    red_coa: COA,
) -> list[IssuedOrder]:
    orders: list[IssuedOrder] = []
    for force_package, coa in ((blue_force, blue_coa), (red_force, red_coa)):
        planned = {action.unit_id: action for action in coa.actions if action.turn == turn}
        for unit in force_package.units:
            action = planned.get(unit.id)
            if action:
                orders.append(
                    IssuedOrder(
                        side=force_package.side,
                        unit_id=unit.id,
                        action=action.action,
                        target_zone=action.target_zone,
                        support_unit_ids=action.support_unit_ids,
                        source_coa_id=coa.id,
                        notes=action.notes,
                    )
                )
            else:
                orders.append(
                    IssuedOrder(
                        side=force_package.side,
                        unit_id=unit.id,
                        action=ActionType.HOLD,
                        source_coa_id=coa.id,
                    )
                )
    return orders


def _update_contact(
    observations: dict[Side, dict[str, dict[str, float | int | str]]],
    observer_side: Side,
    enemy_unit_id: str,
    zone: str,
    confidence: float,
) -> None:
    current = observations[observer_side].get(enemy_unit_id)
    if current and float(current["confidence"]) >= confidence:
        return
    observations[observer_side][enemy_unit_id] = {
        "zone": zone,
        "confidence": round(min(0.99, confidence), 4),
        "age": 0,
    }


def _process_recon(
    turn: int,
    run_id: str,
    unit_states: dict[str, UnitState],
    observations: dict[Side, dict[str, dict[str, float | int | str]]],
    orders: list[IssuedOrder],
    rng: Random,
) -> list[EventLog]:
    events: list[EventLog] = []
    for order in orders:
        if order.action != ActionType.RECON:
            continue
        unit = unit_states[order.unit_id]
        if unit.destroyed:
            continue
        detection_probability = min(0.95, 0.45 + unit.capabilities.isr * 0.05 + unit.readiness * 0.1)
        contacts_found = 0
        for enemy in unit_states.values():
            if enemy.side == unit.side or enemy.destroyed or enemy.location != order.target_zone:
                continue
            if rng.random() <= max(0.2, detection_probability - enemy.signature * 0.15):
                contacts_found += 1
                _update_contact(observations, unit.side, enemy.unit_id, enemy.location, detection_probability)

        unit.supply = max(0.0, round(unit.supply - 0.02, 4))
        unit.fatigue = min(1.0, round(unit.fatigue + 0.03, 4))
        reason_codes = ["successful_recon"] if contacts_found else ["recon_no_contact"]
        result = "recon_contact" if contacts_found else "recon_no_contact"
        events.append(
            _build_event(
                event_id=f"{run_id}_evt_t{turn:02d}_det_{len(events) + 1:03d}",
                run_id=run_id,
                turn=turn,
                phase=Phase.DETECTION,
                actor_side=order.side,
                actor_unit_ids=[order.unit_id],
                action_type=order.action,
                target_zone=order.target_zone,
                inputs={"contacts_found": contacts_found},
                adjudication=AdjudicationResult(
                    feasible=True,
                    detection_probability=round(detection_probability, 4),
                    combat_result=result,
                    reason_codes=reason_codes,
                ),
                confidence=round(detection_probability, 4),
            )
        )
    return events


def _apply_passive_detection(
    scenario: Scenario,
    unit_states: dict[str, UnitState],
    observations: dict[Side, dict[str, dict[str, float | int | str]]],
) -> None:
    adjacency = _adjacency_map(scenario)
    units = [unit for unit in unit_states.values() if not unit.destroyed]
    for observer in units:
        for enemy in units:
            if observer.side == enemy.side:
                continue
            if observer.location == enemy.location:
                _update_contact(observations, observer.side, enemy.unit_id, enemy.location, 0.95)
                continue
            if enemy.location in adjacency.get(observer.location, set()):
                confidence = min(0.8, 0.25 + observer.capabilities.isr * 0.04 - enemy.signature * 0.08)
                if confidence > 0.2:
                    _update_contact(observations, observer.side, enemy.unit_id, enemy.location, confidence)


def _process_movement(
    turn: int,
    run_id: str,
    scenario: Scenario,
    unit_states: dict[str, UnitState],
    orders: list[IssuedOrder],
) -> list[EventLog]:
    adjacency = _adjacency_map(scenario)
    move_orders = [order for order in orders if order.action == ActionType.MOVE]
    events: list[EventLog] = []
    desired_moves: dict[str, str] = {}
    for order in move_orders:
        unit = unit_states[order.unit_id]
        if unit.destroyed:
            continue
        feasible = bool(order.target_zone and order.target_zone in adjacency.get(unit.location, set()))
        reason_codes = ["movement_executed"] if feasible else ["invalid_route"]
        result = "move_completed" if feasible else "move_denied"
        if feasible and order.target_zone:
            desired_moves[order.unit_id] = order.target_zone
        events.append(
            _build_event(
                event_id=f"{run_id}_evt_t{turn:02d}_mov_{len(events) + 1:03d}",
                run_id=run_id,
                turn=turn,
                phase=Phase.MOVEMENT,
                actor_side=order.side,
                actor_unit_ids=[order.unit_id],
                action_type=order.action,
                target_zone=order.target_zone,
                inputs={"origin_zone": unit.location},
                adjudication=AdjudicationResult(
                    feasible=feasible,
                    combat_result=result,
                    reason_codes=reason_codes,
                ),
                confidence=0.95 if feasible else 0.5,
            )
        )

    for unit_id, target_zone in desired_moves.items():
        unit = unit_states[unit_id]
        unit.location = target_zone
        unit.supply = max(0.0, round(unit.supply - 0.05, 4))
        unit.fatigue = min(1.0, round(unit.fatigue + 0.05, 4))

    return events


def _process_support(
    turn: int,
    run_id: str,
    unit_states: dict[str, UnitState],
    orders: list[IssuedOrder],
) -> tuple[dict[str, float], list[EventLog]]:
    support_bonus: dict[str, float] = {}
    events: list[EventLog] = []
    for order in orders:
        if order.action != ActionType.SUPPORT:
            continue
        unit = unit_states[order.unit_id]
        if unit.destroyed:
            continue
        targets = order.support_unit_ids or [
            candidate.unit_id
            for candidate in unit_states.values()
            if candidate.side == unit.side and candidate.location == unit.location and candidate.unit_id != unit.unit_id
        ]
        if not targets:
            result = "support_idle"
            feasible = False
            reason_codes = ["support_no_target"]
        else:
            result = "support_applied"
            feasible = True
            reason_codes = ["coordinated_support"]
            for target in targets:
                support_bonus[target] = support_bonus.get(target, 0.0) + 0.12

        unit.supply = max(0.0, round(unit.supply - 0.03, 4))
        unit.fatigue = min(1.0, round(unit.fatigue + 0.02, 4))
        events.append(
            _build_event(
                event_id=f"{run_id}_evt_t{turn:02d}_sup_{len(events) + 1:03d}",
                run_id=run_id,
                turn=turn,
                phase=Phase.SUPPORT,
                actor_side=order.side,
                actor_unit_ids=[order.unit_id],
                action_type=order.action,
                inputs={"support_targets": targets},
                adjudication=AdjudicationResult(
                    feasible=feasible,
                    combat_result=result,
                    reason_codes=reason_codes,
                ),
                confidence=0.88 if feasible else 0.5,
            )
        )
    return support_bonus, events


def _process_resupply(
    turn: int,
    run_id: str,
    unit_states: dict[str, UnitState],
    orders: list[IssuedOrder],
) -> list[EventLog]:
    events: list[EventLog] = []
    for order in orders:
        if order.action != ActionType.RESUPPLY:
            continue
        unit = unit_states[order.unit_id]
        if unit.destroyed:
            continue
        unit.supply = min(1.0, round(unit.supply + 0.18, 4))
        unit.readiness = min(1.0, round(unit.readiness + 0.05, 4))
        unit.fatigue = max(0.0, round(unit.fatigue - 0.08, 4))
        events.append(
            _build_event(
                event_id=f"{run_id}_evt_t{turn:02d}_res_{len(events) + 1:03d}",
                run_id=run_id,
                turn=turn,
                phase=Phase.SUPPORT,
                actor_side=order.side,
                actor_unit_ids=[order.unit_id],
                action_type=order.action,
                inputs={},
                adjudication=AdjudicationResult(
                    feasible=True,
                    combat_result="resupply_completed",
                    reason_codes=["resupply_completed"],
                ),
                confidence=0.95,
            )
        )
    return events


def _process_attacks(
    turn: int,
    run_id: str,
    scenario: Scenario,
    unit_states: dict[str, UnitState],
    zone_control: dict[str, ControlState],
    observations: dict[Side, dict[str, dict[str, float | int | str]]],
    orders_by_unit: dict[str, IssuedOrder],
    support_bonus: dict[str, float],
    rng: Random,
) -> list[EventLog]:
    adjacency = _adjacency_map(scenario)
    attack_orders = [order for order in orders_by_unit.values() if order.action == ActionType.ATTACK]
    rng.shuffle(attack_orders)
    events: list[EventLog] = []
    terrain_by_zone = {zone.id: zone.terrain.value for zone in scenario.zones}

    for order in attack_orders:
        attacker = unit_states[order.unit_id]
        if attacker.destroyed:
            continue
        current_zone = attacker.location
        target_zone = order.target_zone
        valid_targets = set(adjacency.get(current_zone, set())) | {current_zone}
        feasible = bool(target_zone and target_zone in valid_targets)
        reason_codes: list[str] = []

        if not feasible or not target_zone:
            events.append(
                _build_event(
                    event_id=f"{run_id}_evt_t{turn:02d}_atk_{len(events) + 1:03d}",
                    run_id=run_id,
                    turn=turn,
                    phase=Phase.ENGAGEMENT,
                    actor_side=order.side,
                    actor_unit_ids=[order.unit_id],
                    action_type=order.action,
                    target_zone=target_zone,
                    inputs={"origin_zone": current_zone},
                    adjudication=AdjudicationResult(
                        feasible=False,
                        combat_result="attack_denied",
                        reason_codes=["invalid_attack_route"],
                    ),
                    confidence=0.5,
                )
            )
            continue

        defenders = [
            unit
            for unit in unit_states.values()
            if unit.side != attacker.side and not unit.destroyed and unit.location == target_zone
        ]

        if not defenders:
            attacker.location = target_zone
            attacker.supply = max(0.0, round(attacker.supply - 0.06, 4))
            attacker.fatigue = min(1.0, round(attacker.fatigue + 0.06, 4))
            zone_control[target_zone] = ControlState(attacker.side.value)
            events.append(
                _build_event(
                    event_id=f"{run_id}_evt_t{turn:02d}_atk_{len(events) + 1:03d}",
                    run_id=run_id,
                    turn=turn,
                    phase=Phase.ENGAGEMENT,
                    actor_side=order.side,
                    actor_unit_ids=[order.unit_id],
                    action_type=order.action,
                    target_zone=target_zone,
                    inputs={"origin_zone": current_zone},
                    adjudication=AdjudicationResult(
                        feasible=True,
                        combat_result="zone_seized_unopposed",
                        zone_control_change=True,
                        reason_codes=["unopposed_advance"],
                    ),
                    confidence=0.9,
                )
            )
            continue

        defender_order_types = {
            defender.unit_id: orders_by_unit.get(defender.unit_id).action
            if orders_by_unit.get(defender.unit_id)
            else ActionType.HOLD
            for defender in defenders
        }
        support = support_bonus.get(attacker.unit_id, 0.0)
        if support:
            reason_codes.append("coordinated_support")
        if attacker.supply < 0.45:
            reason_codes.append("low_supply_penalty")
        observed_defenders = [observations[attacker.side].get(defender.unit_id) for defender in defenders]
        intel_bonus = 0.08 if any(contact and float(contact["confidence"]) >= 0.55 for contact in observed_defenders) else 0.0
        if intel_bonus:
            reason_codes.append("successful_recon")

        terrain_bonus = TERRAIN_DEFENSE_BONUS.get(terrain_by_zone[target_zone], 0.0)
        if terrain_by_zone[target_zone] == "urban":
            reason_codes.append("defender_urban_bonus")

        attack_power = _combat_power(attacker, attack=True)
        attack_modifier = 1.0 + support + intel_bonus - max(0.0, 0.12 * (0.5 - attacker.supply))
        attack_modifier -= attacker.fatigue * 0.15
        attack_power *= max(0.45, attack_modifier) * rng.uniform(0.92, 1.08)

        defense_power = 0.0
        for defender in defenders:
            hold_bonus = 0.1 if defender_order_types[defender.unit_id] == ActionType.HOLD else 0.0
            defense_power += _combat_power(defender, attack=False) * (
                1.0 + terrain_bonus + hold_bonus - defender.fatigue * 0.08
            )

        ratio = attack_power / max(defense_power, 0.1)
        if ratio >= 1.15:
            result = "attack_success"
            zone_change = True
            attacker_losses = 0.05 + rng.random() * 0.05
            defender_losses = 0.12 + rng.random() * 0.12
        elif ratio >= 0.92:
            result = "attack_stalemate"
            zone_change = False
            attacker_losses = 0.08 + rng.random() * 0.06
            defender_losses = 0.08 + rng.random() * 0.06
            reason_codes.append("mutual_attrition")
        else:
            result = "attack_repulsed"
            zone_change = False
            attacker_losses = 0.1 + rng.random() * 0.08
            defender_losses = 0.04 + rng.random() * 0.06
            reason_codes.append("attack_repulsed")

        _apply_losses(attacker, attacker_losses)
        for defender in defenders:
            _apply_losses(defender, defender_losses / max(1, len(defenders)))
            _update_contact(observations, attacker.side, defender.unit_id, defender.location, 0.9)
            _update_contact(observations, defender.side, attacker.unit_id, attacker.location, 0.9)

        attacker.supply = max(0.0, round(attacker.supply - 0.08, 4))
        attacker.fatigue = min(1.0, round(attacker.fatigue + 0.08, 4))
        attacker.morale = max(0.0, round(attacker.morale - attacker_losses * 0.25, 4))

        if zone_change and not attacker.destroyed:
            attacker.location = target_zone
            for defender in defenders:
                if defender.destroyed:
                    continue
                _retreat_unit(defender, scenario, unit_states, attacker.side, rng)
            zone_control[target_zone] = ControlState(attacker.side.value)

        blue_losses, red_losses = (
            (attacker_losses, defender_losses)
            if attacker.side == Side.BLUE
            else (defender_losses, attacker_losses)
        )
        confidence = min(0.95, 0.55 + abs(ratio - 1.0) * 0.4)
        events.append(
            _build_event(
                event_id=f"{run_id}_evt_t{turn:02d}_atk_{len(events) + 1:03d}",
                run_id=run_id,
                turn=turn,
                phase=Phase.ENGAGEMENT,
                actor_side=order.side,
                actor_unit_ids=[order.unit_id],
                action_type=order.action,
                target_zone=target_zone,
                inputs={
                    "origin_zone": current_zone,
                    "attacker_support_bonus": round(support, 4),
                    "terrain": terrain_by_zone[target_zone],
                    "defender_count": len(defenders),
                },
                adjudication=AdjudicationResult(
                    feasible=True,
                    detection_probability=min(1.0, 0.4 + intel_bonus + support),
                    combat_result=result,
                    zone_control_change=zone_change,
                    blue_losses=round(min(1.0, blue_losses), 4),
                    red_losses=round(min(1.0, red_losses), 4),
                    reason_codes=sorted(set(reason_codes)),
                ),
                confidence=round(confidence, 4),
            )
        )
    return events


def _combat_power(unit: UnitState, attack: bool) -> float:
    if unit.destroyed:
        return 0.0
    capability_weight = (
        unit.capabilities.maneuver * (0.35 if attack else 0.28)
        + unit.capabilities.fires * 0.25
        + unit.capabilities.isr * (0.06 if attack else 0.08)
        + unit.capabilities.air_defense * 0.04
        + unit.capabilities.sustainment * 0.05
    )
    human_factors = unit.readiness * 2.8 + unit.morale * 2.0 + unit.supply * 2.1
    return unit.strength * (capability_weight + human_factors)


def _apply_losses(unit: UnitState, loss_fraction: float) -> None:
    unit.strength = max(0.0, round(unit.strength - loss_fraction, 4))
    unit.readiness = max(0.0, round(unit.readiness - loss_fraction * 0.4, 4))
    unit.supply = max(0.0, round(unit.supply - loss_fraction * 0.2, 4))
    unit.fatigue = min(1.0, round(unit.fatigue + loss_fraction * 0.35, 4))
    if unit.strength <= 0.1:
        unit.destroyed = True


def _retreat_unit(
    unit: UnitState,
    scenario: Scenario,
    unit_states: dict[str, UnitState],
    attacking_side: Side,
    rng: Random,
) -> None:
    adjacency = _adjacency_map(scenario)
    candidate_zones = list(adjacency.get(unit.location, set()))
    if not candidate_zones:
        return
    friendly_candidates = [
        zone
        for zone in candidate_zones
        if any(
            other.side == unit.side and not other.destroyed and other.location == zone
            for other in unit_states.values()
        )
    ]
    options = friendly_candidates or candidate_zones
    fallback = [
        zone
        for zone in options
        if not any(
            other.side == attacking_side and not other.destroyed and other.location == zone
            for other in unit_states.values()
        )
    ]
    unit.location = rng.choice(fallback or options)
    unit.morale = max(0.0, round(unit.morale - 0.05, 4))


def _recompute_zone_control(
    scenario: Scenario,
    current_control: dict[str, ControlState],
    unit_states: dict[str, UnitState],
) -> dict[str, ControlState]:
    updated = dict(current_control)
    for zone in scenario.zones:
        occupants = {
            unit.side for unit in unit_states.values() if not unit.destroyed and unit.location == zone.id
        }
        if len(occupants) == 2:
            updated[zone.id] = ControlState.CONTESTED
        elif len(occupants) == 1:
            side = next(iter(occupants))
            updated[zone.id] = ControlState(side.value)
    return updated


def _build_side_views(
    observations: dict[Side, dict[str, dict[str, float | int | str]]]
) -> dict[Side, SideObservation]:
    views: dict[Side, SideObservation] = {}
    for side, contacts in observations.items():
        known_enemy_positions = {
            unit_id: str(contact["zone"])
            for unit_id, contact in contacts.items()
            if float(contact["confidence"]) >= 0.35
        }
        views[side] = SideObservation(
            known_enemy_positions=known_enemy_positions,
            contact_confidence={
                unit_id: round(float(contact["confidence"]), 4)
                for unit_id, contact in contacts.items()
            },
            contact_age={unit_id: int(contact["age"]) for unit_id, contact in contacts.items()},
            unknown_contacts=sum(1 for contact in contacts.values() if float(contact["confidence"]) < 0.35),
            intel_confidence=round(
                sum(float(contact["confidence"]) for contact in contacts.values()) / max(1, len(contacts)),
                4,
            ),
        )
    return views


def _compute_scoreboard(
    scenario: Scenario,
    unit_states: dict[str, UnitState],
    zone_control: dict[str, ControlState],
    tempo_counts: dict[Side, int],
    force_unit_count: dict[Side, int],
    current_turn: int,
) -> dict[Side, SideScore]:
    weights = scenario.scoring_weights
    scores: dict[Side, SideScore] = {}

    for side in (Side.BLUE, Side.RED):
        side_units = [unit for unit in unit_states.values() if unit.side == side]
        objective_total = sum(
            objective.weight for objective in scenario.objectives if objective.side == side
        )
        objective_held = 0.0
        for objective in scenario.objectives:
            if objective.side != side:
                continue
            zone_state = zone_control.get(objective.target_zone, ControlState.NEUTRAL)
            if zone_state == ControlState(side.value):
                objective_held += objective.weight
            elif zone_state == ControlState.CONTESTED:
                objective_held += objective.weight * 0.5

        objective_control = objective_held / max(0.0001, objective_total)
        force_preservation = sum(unit.strength for unit in side_units) / max(1, len(side_units))
        sustainment = sum(unit.supply for unit in side_units) / max(1, len(side_units))
        tempo = min(1.0, tempo_counts[side] / max(1, force_unit_count[side] * current_turn))
        weighted_sum = (
            objective_control * weights["objective_control"]
            + force_preservation * weights["force_preservation"]
            + sustainment * weights["sustainment"]
            + tempo * weights["tempo"]
        )
        scores[side] = SideScore(
            objective_control=round(objective_control, 4),
            force_preservation=round(force_preservation, 4),
            sustainment=round(sustainment, 4),
            tempo=round(tempo, 4),
            overall_score=round(weighted_sum, 4),
        )
    return scores


def _build_event(
    event_id: str,
    run_id: str,
    turn: int,
    phase: Phase,
    actor_side: Side,
    actor_unit_ids: list[str],
    action_type: ActionType,
    inputs: dict[str, object],
    adjudication: AdjudicationResult,
    confidence: float,
    target_zone: str | None = None,
) -> EventLog:
    visibility = {
        "public": EventVisibility.PUBLIC,
        Side.BLUE: EventVisibility.SIDE_VISIBLE,
        Side.RED: EventVisibility.SIDE_VISIBLE,
    }
    return EventLog(
        id=event_id,
        created_at=utc_now_iso(),
        source_run_id=run_id,
        run_id=run_id,
        turn=turn,
        phase=phase,
        actor_side=actor_side,
        actor_unit_ids=actor_unit_ids,
        action_type=action_type,
        target_zone=target_zone,
        inputs=inputs,
        adjudication=adjudication,
        visibility=visibility,
        confidence=confidence,
    )
