from __future__ import annotations

from oeg.planners.base import Planner
from oeg.planners.base import PlannerContext
from oeg.schemas.models import ActionType
from oeg.schemas.models import COA
from oeg.schemas.models import IssuedOrder


class COAPlanner(Planner):
    def __init__(self, coa: COA) -> None:
        self._coa = coa

    @property
    def planner_id(self) -> str:
        return self._coa.id

    def plan_turn(self, context: PlannerContext) -> list[IssuedOrder]:
        actions_by_unit = {
            action.unit_id: action for action in self._coa.actions if action.turn == context.turn_number
        }
        orders: list[IssuedOrder] = []
        for unit in context.force_package.units:
            action = actions_by_unit.get(unit.id)
            if action:
                orders.append(
                    IssuedOrder(
                        side=context.side,
                        unit_id=unit.id,
                        action=action.action,
                        target_zone=action.target_zone,
                        support_unit_ids=action.support_unit_ids,
                        source_coa_id=self.planner_id,
                        notes=action.notes,
                    )
                )
            else:
                orders.append(
                    IssuedOrder(
                        side=context.side,
                        unit_id=unit.id,
                        action=ActionType.HOLD,
                        source_coa_id=self.planner_id,
                    )
                )
        return orders
