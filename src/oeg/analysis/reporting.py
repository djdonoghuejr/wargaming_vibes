from __future__ import annotations

from collections import Counter
from statistics import pstdev

from oeg.schemas.models import AAR
from oeg.schemas.models import COAAggregateResult
from oeg.schemas.models import COAComparison
from oeg.schemas.models import DecisionSummary
from oeg.schemas.models import EventLog
from oeg.schemas.models import LessonLearned
from oeg.schemas.models import RunManifest
from oeg.schemas.models import Scenario
from oeg.schemas.models import Side
from oeg.schemas.models import SideScore
from oeg.storage.io import timestamp_id
from oeg.storage.io import utc_now_iso


LESSON_TEMPLATES = {
    "successful_recon": (
        "Recon actions improved contact certainty before engagement.",
        "ISR quality materially shapes engagement timing and attack confidence.",
        "Use recon to confirm likely enemy positions before committing main-effort attacks.",
        ["ISR", "recon"],
    ),
    "low_supply_penalty": (
        "Supply shortfalls degraded combat performance during the run.",
        "Sustainment fragility can outweigh local combat power when engagements extend across multiple turns.",
        "Schedule deliberate resupply windows before launching repeated attacks.",
        ["sustainment", "logistics"],
    ),
    "defender_urban_bonus": (
        "Urban terrain provided a meaningful defensive advantage.",
        "Key terrain can compress attacker options and increase attrition on direct approaches.",
        "Avoid frontal assaults into urban zones without support or prior shaping actions.",
        ["terrain", "defense"],
    ),
    "coordinated_support": (
        "Coordinated support increased the effectiveness of main-effort actions.",
        "Synchronization between support and maneuver improved the probability of favorable outcomes.",
        "Pair support tasks with the turn and unit designated as the main effort.",
        ["coordination", "support"],
    ),
}


def _describe_event(event: EventLog) -> str:
    actor = ", ".join(event.actor_unit_ids)
    result = event.adjudication.combat_result.replace("_", " ")
    if event.target_zone:
        return (
            f"Turn {event.turn}: {event.actor_side.value} {event.action_type.value} by "
            f"{actor} at {event.target_zone} resulted in {result}."
        )
    return (
        f"Turn {event.turn}: {event.actor_side.value} {event.action_type.value} by "
        f"{actor} resulted in {result}."
    )


def _impact_score(event: EventLog) -> float:
    score = event.adjudication.blue_losses + event.adjudication.red_losses
    if event.adjudication.zone_control_change:
        score += 0.35
    if event.action_type.value == "attack":
        score += 0.15
    return score


def _mission_outcome(blue: SideScore, red: SideScore) -> str:
    delta = blue.overall_score - red.overall_score
    if delta >= 0.1:
        return "blue_success"
    if delta >= 0.03:
        return "blue_marginal_success"
    if delta <= -0.1:
        return "red_success"
    if delta <= -0.03:
        return "red_marginal_success"
    return "draw"


def extract_lessons(event_logs: list[EventLog], run_id: str) -> list[LessonLearned]:
    reason_counter = Counter()
    reason_to_events: dict[str, list[str]] = {}
    for event in event_logs:
        for code in event.adjudication.reason_codes:
            reason_counter[code] += 1
            reason_to_events.setdefault(code, []).append(event.id)

    lessons: list[LessonLearned] = []
    for index, (code, count) in enumerate(reason_counter.most_common(2), start=1):
        observation, implication, action, tags = LESSON_TEMPLATES.get(
            code,
            (
                f"The pattern '{code}' appeared repeatedly across the run.",
                "Repeated adjudication factors should inform future COA design.",
                "Review the associated event evidence before repeating the same pattern.",
                ["pattern"],
            ),
        )
        lessons.append(
            LessonLearned(
                id=f"{run_id}_lesson_{index:02d}",
                created_at=utc_now_iso(),
                source_run_id=run_id,
                observation=observation,
                conditions=[code],
                evidence_event_ids=reason_to_events.get(code, [])[:5],
                implication=implication,
                recommended_action=action,
                confidence=min(0.95, 0.55 + 0.08 * count),
                tags=tags,
            )
        )
    return lessons


def build_aar(
    scenario: Scenario,
    manifest: RunManifest,
    event_logs: list[EventLog],
    lessons: list[LessonLearned],
) -> AAR:
    blue_score = manifest.summary_scores[Side.BLUE]
    red_score = manifest.summary_scores[Side.RED]
    impactful_events = sorted(event_logs, key=_impact_score, reverse=True)
    timeline_highlights = [_describe_event(event) for event in impactful_events[:4]]

    key_decisions = [
        DecisionSummary(
            turn=event.turn,
            side=event.actor_side,
            decision=f"{event.action_type.value} by {', '.join(event.actor_unit_ids)}",
            effect=event.adjudication.combat_result.replace("_", " "),
        )
        for event in impactful_events[:3]
    ]

    reason_codes = Counter()
    for event in event_logs:
        for code in event.adjudication.reason_codes:
            reason_codes[code] += 1

    metric_summary = {
        "blue_overall_score": round(blue_score.overall_score, 3),
        "red_overall_score": round(red_score.overall_score, 3),
        "blue_objective_control": round(blue_score.objective_control, 3),
        "red_objective_control": round(red_score.objective_control, 3),
        "blue_force_preservation": round(blue_score.force_preservation, 3),
        "red_force_preservation": round(red_score.force_preservation, 3),
        "blue_sustainment": round(blue_score.sustainment, 3),
        "red_sustainment": round(red_score.sustainment, 3),
        "blue_tempo": round(blue_score.tempo, 3),
        "red_tempo": round(red_score.tempo, 3),
    }

    return AAR(
        id=f"{manifest.id}_aar",
        created_at=utc_now_iso(),
        source_run_id=manifest.id,
        run_id=manifest.id,
        scenario_id=scenario.id,
        mission_outcome=_mission_outcome(blue_score, red_score),
        metric_summary=metric_summary,
        timeline_highlights=timeline_highlights,
        key_decisions=key_decisions,
        causal_factors=[code.replace("_", " ") for code, _ in reason_codes.most_common(4)],
        lesson_ids=[lesson.id for lesson in lessons],
        recommended_actions=[lesson.recommended_action for lesson in lessons],
    )


def _mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def _mean_side_score(manifests: list[RunManifest], side: Side, attribute: str) -> float:
    return _mean([getattr(manifest.summary_scores[side], attribute) for manifest in manifests])


def aggregate_comparison(
    scenario: Scenario,
    manifests_by_coa: dict[str, list[RunManifest]],
    red_coa_id: str,
    seed_list: list[int],
) -> COAComparison:
    metric_results: dict[str, COAAggregateResult] = {}
    run_ids_by_coa: dict[str, list[str]] = {}
    score_vectors: dict[str, list[float]] = {}

    for coa_id, manifests in manifests_by_coa.items():
        run_ids_by_coa[coa_id] = [manifest.id for manifest in manifests]
        score_vectors[coa_id] = [manifest.summary_scores[Side.BLUE].overall_score for manifest in manifests]
        metric_results[coa_id] = COAAggregateResult(
            mean_overall_score=_mean_side_score(manifests, Side.BLUE, "overall_score"),
            mean_objective_control=_mean_side_score(manifests, Side.BLUE, "objective_control"),
            mean_force_preservation=_mean_side_score(manifests, Side.BLUE, "force_preservation"),
            mean_sustainment=_mean_side_score(manifests, Side.BLUE, "sustainment"),
            mean_tempo=_mean_side_score(manifests, Side.BLUE, "tempo"),
            casualty_index=1.0 - _mean_side_score(manifests, Side.BLUE, "force_preservation"),
        )

    ranked = sorted(
        metric_results.items(),
        key=lambda item: (
            item[1].mean_overall_score,
            item[1].mean_objective_control,
            -item[1].casualty_index,
        ),
        reverse=True,
    )
    best_id, best_metrics = ranked[0]
    runner_up_id, runner_up_metrics = ranked[1]
    best_vector = score_vectors[best_id]
    confidence = max(
        0.5,
        min(
            0.99,
            0.55
            + abs(best_metrics.mean_overall_score - runner_up_metrics.mean_overall_score) * 2.0
            - pstdev(best_vector) * 0.5,
        ),
    )

    if best_metrics.casualty_index <= runner_up_metrics.casualty_index:
        tradeoffs = (
            f"{best_id} delivered better objective retention with lower expected casualties than {runner_up_id}."
        )
    else:
        tradeoffs = (
            f"{best_id} improved objective retention over {runner_up_id}, but at higher expected casualty cost."
        )

    return COAComparison(
        id=timestamp_id("comparison"),
        created_at=utc_now_iso(),
        scenario_id=scenario.id,
        coa_ids=list(manifests_by_coa.keys()),
        red_coa_id=red_coa_id,
        seed_list=seed_list,
        sample_count=len(seed_list),
        metric_results=metric_results,
        paired_seed_stats={
            "score_delta": round(best_metrics.mean_overall_score - runner_up_metrics.mean_overall_score, 4),
            "objective_delta": round(
                best_metrics.mean_objective_control - runner_up_metrics.mean_objective_control, 4
            ),
            "casualty_delta": round(
                runner_up_metrics.casualty_index - best_metrics.casualty_index,
                4,
            ),
            "confidence": round(confidence, 4),
        },
        recommended_coa=best_id,
        tradeoffs=tradeoffs,
        run_ids_by_coa=run_ids_by_coa,
    )
