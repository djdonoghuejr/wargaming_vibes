from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Side(str, Enum):
    BLUE = "blue"
    RED = "red"


class ControlState(str, Enum):
    BLUE = "blue"
    RED = "red"
    CONTESTED = "contested"
    NEUTRAL = "neutral"


class TerrainType(str, Enum):
    URBAN = "urban"
    OPEN = "open"
    ELEVATED_OPEN = "elevated_open"
    INDUSTRIAL = "industrial"
    AIRFIELD = "airfield"


class ObjectiveType(str, Enum):
    HOLD_ZONE = "hold_zone"
    SEIZE_ZONE = "seize_zone"
    KEEP_ZONE_OPERATIONAL = "keep_zone_operational"


class ActionType(str, Enum):
    MOVE = "move"
    HOLD = "hold"
    RECON = "recon"
    ATTACK = "attack"
    RESUPPLY = "resupply"
    SUPPORT = "support"


class Phase(str, Enum):
    ORDER_INTAKE = "order_intake"
    DETECTION = "detection"
    MOVEMENT = "movement"
    SUPPORT = "support"
    ENGAGEMENT = "engagement"
    SCORING = "scoring"
    COMPLETED = "completed"


class EventVisibility(str, Enum):
    PUBLIC = "public"
    SIDE_VISIBLE = "side_visible"
    HIDDEN = "hidden"


class Artifact(StrictModel):
    id: str
    schema_version: str = "0.1.0"
    created_at: str | None = None
    source_run_id: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class Zone(StrictModel):
    id: str
    name: str
    terrain: TerrainType
    strategic_value: int = Field(default=5, ge=1, le=10)


class ZoneEdge(StrictModel):
    a: str
    b: str
    distance: int = Field(default=1, ge=1, le=5)


class Environment(StrictModel):
    weather: str
    visibility: str = "standard"
    notes: list[str] = Field(default_factory=list)


class ScenarioObjective(StrictModel):
    id: str
    side: Side
    objective_type: ObjectiveType
    target_zone: str
    description: str
    weight: float = Field(default=1.0, gt=0.0, le=10.0)


class Scenario(Artifact):
    name: str
    description: str
    classification: str = "exercise-use-only"
    turn_duration_hours: int = Field(default=6, ge=1, le=24)
    max_turns: int = Field(default=6, ge=1, le=24)
    zones: list[Zone] = Field(min_length=1)
    edges: list[ZoneEdge] = Field(min_length=1)
    initial_zone_control: dict[str, ControlState]
    objectives: list[ScenarioObjective] = Field(min_length=1)
    environment: Environment
    constraints: dict[Side, list[str]] = Field(default_factory=dict)
    victory_metrics: list[str] = Field(
        default_factory=lambda: [
            "objective_control",
            "force_preservation",
            "sustainment",
            "tempo",
        ]
    )
    scoring_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "objective_control": 0.4,
            "force_preservation": 0.25,
            "sustainment": 0.2,
            "tempo": 0.15,
        }
    )


class CapabilitySet(StrictModel):
    maneuver: int = Field(ge=0, le=10)
    fires: int = Field(ge=0, le=10)
    isr: int = Field(ge=0, le=10)
    air_defense: int = Field(ge=0, le=10)
    sustainment: int = Field(ge=0, le=10)


class Unit(StrictModel):
    id: str
    label: str
    echelon: str
    location: str
    readiness: float = Field(ge=0.0, le=1.0)
    morale: float = Field(ge=0.0, le=1.0)
    supply: float = Field(ge=0.0, le=1.0)
    signature: float = Field(ge=0.0, le=1.0)
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    fatigue: float = Field(default=0.1, ge=0.0, le=1.0)
    capabilities: CapabilitySet


class ForcePackage(Artifact):
    side: Side
    name: str
    doctrine: str
    units: list[Unit] = Field(min_length=1)
    support_assets: dict[str, int] = Field(default_factory=dict)
    capability_summary: dict[str, float] = Field(default_factory=dict)


class PlannedAction(StrictModel):
    turn: int = Field(ge=1)
    unit_id: str
    action: ActionType
    target_zone: str | None = None
    support_unit_ids: list[str] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "PlannedAction":
        if self.action in {ActionType.MOVE, ActionType.RECON, ActionType.ATTACK} and not self.target_zone:
            raise ValueError(f"{self.action.value} requires target_zone")
        return self


class COA(Artifact):
    side: Side
    name: str
    description: str
    strategy_tags: list[str] = Field(default_factory=list)
    actions: list[PlannedAction] = Field(default_factory=list)


class IssuedOrder(StrictModel):
    side: Side
    unit_id: str
    action: ActionType
    target_zone: str | None = None
    support_unit_ids: list[str] = Field(default_factory=list)
    source_coa_id: str
    notes: str | None = None


class SideObservation(StrictModel):
    known_enemy_positions: dict[str, str] = Field(default_factory=dict)
    contact_confidence: dict[str, float] = Field(default_factory=dict)
    contact_age: dict[str, int] = Field(default_factory=dict)
    unknown_contacts: int = Field(default=0, ge=0)
    intel_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SideScore(StrictModel):
    objective_control: float = Field(default=0.0, ge=0.0, le=1.0)
    force_preservation: float = Field(default=0.0, ge=0.0, le=1.0)
    sustainment: float = Field(default=0.0, ge=0.0, le=1.0)
    tempo: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)


class UnitState(StrictModel):
    unit_id: str
    side: Side
    label: str
    location: str
    strength: float = Field(ge=0.0, le=1.0)
    readiness: float = Field(ge=0.0, le=1.0)
    morale: float = Field(ge=0.0, le=1.0)
    supply: float = Field(ge=0.0, le=1.0)
    fatigue: float = Field(ge=0.0, le=1.0)
    signature: float = Field(ge=0.0, le=1.0)
    capabilities: CapabilitySet
    destroyed: bool = False


class TruthState(StrictModel):
    zone_control: dict[str, ControlState]
    unit_status: dict[str, UnitState]


class TurnState(Artifact):
    run_id: str
    turn_number: int = Field(ge=1)
    phase: Phase
    rng_seed: int
    truth_state: TruthState
    side_views: dict[Side, SideObservation]
    scoreboard: dict[Side, SideScore]
    active_orders: list[IssuedOrder]


class AdjudicationResult(StrictModel):
    feasible: bool
    detection_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    combat_result: str
    zone_control_change: bool = False
    blue_losses: float = Field(default=0.0, ge=0.0, le=1.0)
    red_losses: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)


class EventLog(Artifact):
    run_id: str
    turn: int = Field(ge=1)
    phase: Phase
    actor_side: Side
    actor_unit_ids: list[str] = Field(min_length=1)
    action_type: ActionType
    target_zone: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    adjudication: AdjudicationResult
    visibility: dict[Side | str, EventVisibility] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DecisionSummary(StrictModel):
    turn: int = Field(ge=1)
    side: Side
    decision: str
    effect: str


class LessonLearned(Artifact):
    observation: str
    conditions: list[str] = Field(default_factory=list)
    evidence_event_ids: list[str] = Field(default_factory=list)
    implication: str
    recommended_action: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)


class AAR(Artifact):
    run_id: str
    scenario_id: str
    mission_outcome: str
    metric_summary: dict[str, float] = Field(default_factory=dict)
    timeline_highlights: list[str] = Field(default_factory=list)
    key_decisions: list[DecisionSummary] = Field(default_factory=list)
    causal_factors: list[str] = Field(default_factory=list)
    lesson_ids: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class COAAggregateResult(StrictModel):
    mean_overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    mean_objective_control: float = Field(default=0.0, ge=0.0, le=1.0)
    mean_force_preservation: float = Field(default=0.0, ge=0.0, le=1.0)
    mean_sustainment: float = Field(default=0.0, ge=0.0, le=1.0)
    mean_tempo: float = Field(default=0.0, ge=0.0, le=1.0)
    casualty_index: float = Field(default=0.0, ge=0.0, le=1.0)


class COAComparison(Artifact):
    scenario_id: str
    coa_ids: list[str] = Field(min_length=2)
    red_coa_id: str
    seed_list: list[int] = Field(min_length=1)
    sample_count: int = Field(ge=1)
    metric_results: dict[str, COAAggregateResult]
    paired_seed_stats: dict[str, float] = Field(default_factory=dict)
    recommended_coa: str
    tradeoffs: str
    run_ids_by_coa: dict[str, list[str]] = Field(default_factory=dict)


class RunManifest(Artifact):
    scenario_id: str
    blue_force_package_id: str
    red_force_package_id: str
    blue_coa_id: str
    red_coa_id: str
    seed: int
    turns_completed: int = Field(ge=1)
    output_dir: str | None = None
    summary_scores: dict[Side, SideScore]
    final_outcome: str
