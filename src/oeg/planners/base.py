from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass

from oeg.schemas.models import ForcePackage
from oeg.schemas.models import IssuedOrder
from oeg.schemas.models import Scenario
from oeg.schemas.models import ScenarioObjective
from oeg.schemas.models import Side
from oeg.schemas.models import SideObservation
from oeg.schemas.models import UnitState


@dataclass(frozen=True)
class PlannerContext:
    run_id: str
    turn_number: int
    side: Side
    scenario: Scenario
    force_package: ForcePackage
    own_units: dict[str, UnitState]
    side_view: SideObservation
    objectives: list[ScenarioObjective]
    adjacency_map: dict[str, set[str]]


class Planner(ABC):
    @property
    @abstractmethod
    def planner_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def plan_turn(self, context: PlannerContext) -> list[IssuedOrder]:
        raise NotImplementedError
