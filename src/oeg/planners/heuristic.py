from __future__ import annotations

from collections import deque

from oeg.planners.base import Planner
from oeg.planners.base import PlannerContext
from oeg.schemas.models import ActionType
from oeg.schemas.models import IssuedOrder
from oeg.schemas.models import ObjectiveType
from oeg.schemas.models import ScenarioObjective
from oeg.schemas.models import UnitState


class HeuristicPlanner(Planner):
    def __init__(self, name: str = "heuristic_balanced") -> None:
        self._planner_id = name

    @property
    def planner_id(self) -> str:
        return self._planner_id

    def plan_turn(self, context: PlannerContext) -> list[IssuedOrder]:
        objectives = sorted(context.objectives, key=lambda item: item.weight, reverse=True)
        primary = objectives[0] if objectives else None
        secondary = objectives[1] if len(objectives) > 1 else primary
        primary_target = primary.target_zone if primary else None
        secondary_target = secondary.target_zone if secondary else primary_target
        known_enemy_zones = set(context.side_view.known_enemy_positions.values())
        suspected_enemy_zones = set(context.side_view.suspected_enemy_zones)
        false_contact_zones = set(context.side_view.false_contact_zones)

        planned: dict[str, IssuedOrder] = {}
        attack_candidates: list[str] = []

        units = sorted(
            context.own_units.values(),
            key=lambda unit: (
                unit.destroyed,
                -unit.capabilities.isr,
                -unit.capabilities.maneuver,
                unit.unit_id,
            ),
        )

        for unit in units:
            if unit.destroyed:
                planned[unit.unit_id] = self._hold_order(context, unit, "unit_destroyed")
                continue

            if unit.supply <= 0.28:
                planned[unit.unit_id] = IssuedOrder(
                    side=context.side,
                    unit_id=unit.unit_id,
                    action=ActionType.RESUPPLY,
                    source_coa_id=self.planner_id,
                    notes="Low supply triggered a resupply action.",
                )
                continue

            if unit.capabilities.isr >= 7 and primary_target and (
                context.turn_number <= 2 or context.side_view.intel_confidence < 0.5
            ):
                recon_target = self._choose_recon_zone(context, primary_target, secondary_target)
                planned[unit.unit_id] = IssuedOrder(
                    side=context.side,
                    unit_id=unit.unit_id,
                    action=ActionType.RECON,
                    target_zone=recon_target,
                    source_coa_id=self.planner_id,
                    notes="ISR-heavy unit refreshing the contact picture.",
                )
                continue

            objective = self._assign_objective(unit, objectives)
            objective_target = objective.target_zone if objective else primary_target
            if not objective_target:
                planned[unit.unit_id] = self._hold_order(context, unit, "no_objective")
                continue

            if (
                objective.objective_type in {ObjectiveType.HOLD_ZONE, ObjectiveType.KEEP_ZONE_OPERATIONAL}
                and unit.location == objective_target
            ):
                if suspected_enemy_zones and unit.capabilities.isr >= 4:
                    recon_target = self._best_local_recon_target(context, unit.location, suspected_enemy_zones)
                    if recon_target:
                        planned[unit.unit_id] = IssuedOrder(
                            side=context.side,
                            unit_id=unit.unit_id,
                            action=ActionType.RECON,
                            target_zone=recon_target,
                            source_coa_id=self.planner_id,
                            notes="Checking likely approach lane while holding key terrain.",
                        )
                        continue
                planned[unit.unit_id] = self._hold_order(context, unit, "holding_key_terrain")
                continue

            if objective_target in context.adjacency_map.get(unit.location, set()) | {unit.location}:
                if objective_target in false_contact_zones and unit.capabilities.isr >= 5:
                    planned[unit.unit_id] = IssuedOrder(
                        side=context.side,
                        unit_id=unit.unit_id,
                        action=ActionType.RECON,
                        target_zone=objective_target,
                        source_coa_id=self.planner_id,
                        notes="Validating a low-confidence contact before attacking.",
                    )
                elif objective_target in known_enemy_zones or objective.objective_type == ObjectiveType.SEIZE_ZONE:
                    planned[unit.unit_id] = IssuedOrder(
                        side=context.side,
                        unit_id=unit.unit_id,
                        action=ActionType.ATTACK,
                        target_zone=objective_target,
                        source_coa_id=self.planner_id,
                        notes=f"Directly contesting objective zone {objective_target}.",
                    )
                    attack_candidates.append(unit.unit_id)
                elif objective_target in suspected_enemy_zones and unit.capabilities.isr >= 4:
                    planned[unit.unit_id] = IssuedOrder(
                        side=context.side,
                        unit_id=unit.unit_id,
                        action=ActionType.RECON,
                        target_zone=objective_target,
                        source_coa_id=self.planner_id,
                        notes=f"Clarifying suspected enemy presence near {objective_target}.",
                    )
                else:
                    planned[unit.unit_id] = IssuedOrder(
                        side=context.side,
                        unit_id=unit.unit_id,
                        action=ActionType.MOVE,
                        target_zone=objective_target,
                        source_coa_id=self.planner_id,
                        notes=f"Moving to reinforce objective zone {objective_target}.",
                    )
                continue

            next_zone = self._next_step(context, unit.location, objective_target)
            if next_zone:
                planned[unit.unit_id] = IssuedOrder(
                    side=context.side,
                    unit_id=unit.unit_id,
                    action=ActionType.MOVE,
                    target_zone=next_zone,
                    source_coa_id=self.planner_id,
                    notes=f"Advancing along the route to {objective_target}.",
                )
            else:
                planned[unit.unit_id] = self._hold_order(context, unit, "no_route")

        if attack_candidates:
            for unit in units:
                if unit.destroyed or unit.unit_id in planned and planned[unit.unit_id].action != ActionType.HOLD:
                    continue
                if unit.capabilities.fires >= 7 or (
                    unit.capabilities.fires >= 4 and unit.location == context.own_units[attack_candidates[0]].location
                ):
                    planned[unit.unit_id] = IssuedOrder(
                        side=context.side,
                        unit_id=unit.unit_id,
                        action=ActionType.SUPPORT,
                        support_unit_ids=[attack_candidates[0]],
                        source_coa_id=self.planner_id,
                        notes=f"Supporting the main-effort unit {attack_candidates[0]}.",
                    )
                    break

        return [planned[unit.id] for unit in context.force_package.units if unit.id in planned]

    def _assign_objective(
        self,
        unit: UnitState,
        objectives: list[ScenarioObjective],
    ) -> ScenarioObjective | None:
        if not objectives:
            return None
        if unit.capabilities.isr >= 7 and len(objectives) > 1:
            return objectives[1]
        return objectives[0]

    def _choose_recon_zone(
        self,
        context: PlannerContext,
        primary_target: str,
        secondary_target: str | None,
    ) -> str:
        if context.side_view.known_enemy_positions:
            ranked = sorted(
                context.side_view.known_enemy_positions.values(),
                key=lambda zone: (zone != primary_target, zone != secondary_target, zone),
            )
            return ranked[0]
        if context.side_view.suspected_enemy_zones:
            ranked = sorted(
                context.side_view.suspected_enemy_zones,
                key=lambda zone: (zone != primary_target, zone != secondary_target, zone),
            )
            return ranked[0]
        return secondary_target or primary_target

    def _next_step(self, context: PlannerContext, start: str, goal: str) -> str | None:
        if start == goal:
            return goal
        queue: deque[tuple[str, list[str]]] = deque([(start, [start])])
        visited = {start}
        while queue:
            zone, path = queue.popleft()
            for neighbor in sorted(context.adjacency_map.get(zone, set())):
                if neighbor in visited:
                    continue
                if neighbor == goal:
                    return path[1] if len(path) > 1 else neighbor
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
        return None

    def _best_local_recon_target(
        self,
        context: PlannerContext,
        origin_zone: str,
        suspected_enemy_zones: set[str],
    ) -> str | None:
        adjacent = context.adjacency_map.get(origin_zone, set()) | {origin_zone}
        local_candidates = sorted(adjacent & suspected_enemy_zones)
        if local_candidates:
            return local_candidates[0]
        if suspected_enemy_zones:
            return sorted(suspected_enemy_zones)[0]
        return None

    def _hold_order(
        self,
        context: PlannerContext,
        unit: UnitState,
        reason: str,
    ) -> IssuedOrder:
        return IssuedOrder(
            side=context.side,
            unit_id=unit.unit_id,
            action=ActionType.HOLD,
            source_coa_id=self.planner_id,
            notes=reason,
        )
