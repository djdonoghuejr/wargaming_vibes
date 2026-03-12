from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from oeg.paths import default_analysis_dir
from oeg.paths import default_catalog_path
from oeg.paths import default_generated_dir
from oeg.paths import default_runs_dir
from oeg.paths import project_root
from oeg.paths import template_dir


class CatalogUnavailableError(RuntimeError):
    pass


class ResourceNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApiSettings:
    project_root: Path
    catalog_path: Path
    runs_dir: Path
    templates_dir: Path
    analysis_dir: Path
    generated_dir: Path


def default_api_settings() -> ApiSettings:
    return ApiSettings(
        project_root=project_root(),
        catalog_path=default_catalog_path(),
        runs_dir=default_runs_dir(),
        templates_dir=template_dir(),
        analysis_dir=default_analysis_dir(),
        generated_dir=default_generated_dir(),
    )


class AnalystDataService:
    def __init__(self, settings: ApiSettings) -> None:
        self.settings = settings

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "catalog_path": str(self.settings.catalog_path),
            "catalog_exists": self.settings.catalog_path.exists(),
        }

    def summary(self) -> dict[str, Any]:
        counts = self._query_one(
            """
            SELECT
              (SELECT COUNT(*) FROM templates) AS template_count,
              (SELECT COUNT(*) FROM approved_templates) AS approved_template_count,
              (SELECT COUNT(*) FROM run_manifests) AS run_count,
              (SELECT COUNT(*) FROM comparisons) AS comparison_count,
              (SELECT COUNT(*) FROM lessons) AS lesson_count,
              (SELECT COUNT(*) FROM aars) AS aar_count
            """
        )
        return {
            "catalog_path": str(self.settings.catalog_path),
            "counts": {
                "templates": counts["template_count"],
                "approved_templates": counts["approved_template_count"],
                "runs": counts["run_count"],
                "comparisons": counts["comparison_count"],
                "lessons": counts["lesson_count"],
                "aars": counts["aar_count"],
            },
            "recent_runs": self._list_recent_runs(limit=5),
            "recent_comparisons": self._list_recent_comparisons(limit=5),
            "recent_templates": self._list_recent_templates(limit=5),
        }

    def list_templates(
        self,
        *,
        template_kind: str | None = None,
        approval_state: str | None = None,
        side: str | None = None,
        doctrine: str | None = None,
        base_asset_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "quality_score",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        allowed_sorts = {
            "quality_score": "COALESCE(q.quality_score, 0)",
            "template_id": "t.template_id",
            "template_kind": "t.template_kind",
            "approval_state": "COALESCE(q.approval_state, 'unknown')",
            "name": "COALESCE(t.name, t.template_id)",
        }
        base_query = """
            FROM templates t
            LEFT JOIN template_quality q ON t.template_id = q.template_id
            WHERE 1 = 1
        """
        conditions: list[str] = []
        params: list[Any] = []
        if template_kind:
            conditions.append("AND t.template_kind = ?")
            params.append(template_kind)
        if approval_state:
            conditions.append("AND q.approval_state = ?")
            params.append(approval_state)
        if side:
            conditions.append("AND t.side = ?")
            params.append(side)
        if doctrine:
            conditions.append("AND t.doctrine = ?")
            params.append(doctrine)
        if base_asset_id:
            conditions.append("AND t.base_asset_id = ?")
            params.append(base_asset_id)

        where_sql = " ".join(conditions)
        total = self._query_scalar(f"SELECT COUNT(*) {base_query} {where_sql}", params)
        order_sql = allowed_sorts.get(sort_by, allowed_sorts["quality_score"])
        direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
        rows = self._query(
            f"""
            SELECT
              t.template_id,
              t.template_kind,
              t.name,
              t.description,
              t.base_asset_id,
              t.side,
              t.doctrine,
              t.template_path,
              t.weather_option_count,
              t.visibility_option_count,
              t.zone_adjustment_count,
              t.unit_variability_count,
              t.action_variation_count,
              q.quality_score,
              q.quality_band,
              q.approval_state,
              q.warning_count,
              q.warnings
            {base_query}
            {where_sql}
            ORDER BY {order_sql} {direction}, t.template_id ASC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        return {"total": total, "limit": limit, "offset": offset, "items": rows}

    def get_template_detail(self, template_id: str) -> dict[str, Any]:
        row = self._query_one(
            """
            SELECT
              t.*,
              q.quality_score,
              q.quality_band,
              q.approval_state,
              q.warning_count,
              q.warnings
            FROM templates t
            LEFT JOIN template_quality q ON t.template_id = q.template_id
            WHERE t.template_id = ?
            """,
            [template_id],
        )
        if not row:
            raise ResourceNotFoundError(f"Template '{template_id}' was not found.")

        raw_template = json.loads(Path(row["template_path"]).read_text(encoding="utf-8"))
        return {
            "summary": row,
            "raw_template": raw_template,
            "related_runs": self._related_runs_for_template(row),
            "related_comparisons": self._related_comparisons_for_template(row),
        }

    def list_runs(
        self,
        *,
        scenario_id: str | None = None,
        source_template_id: str | None = None,
        seed: int | None = None,
        stochastic_profile_id: str | None = None,
        quality_band: str | None = None,
        final_outcome: str | None = None,
        blue_actor_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "run_id",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        allowed_sorts = {
            "run_id": "r.run_id",
            "blue_overall_score": "r.blue_overall_score",
            "red_overall_score": "r.red_overall_score",
            "quality_score": "COALESCE(r.quality_score, 0)",
            "final_outcome": "r.final_outcome",
        }
        base_query = "FROM run_with_quality r WHERE 1 = 1"
        conditions: list[str] = []
        params: list[Any] = []
        if scenario_id:
            conditions.append("AND r.scenario_id = ?")
            params.append(scenario_id)
        if source_template_id:
            conditions.append(
                "AND (r.source_scenario_template_id = ? OR r.source_blue_force_template_id = ? "
                "OR r.source_red_force_template_id = ? OR r.source_blue_coa_template_id = ? OR r.source_red_coa_template_id = ?)"
            )
            params.extend([source_template_id] * 5)
        if seed is not None:
            conditions.append("AND r.seed = ?")
            params.append(seed)
        if stochastic_profile_id:
            conditions.append("AND r.stochastic_profile_id = ?")
            params.append(stochastic_profile_id)
        if quality_band:
            conditions.append("AND r.quality_band = ?")
            params.append(quality_band)
        if final_outcome:
            conditions.append("AND r.final_outcome = ?")
            params.append(final_outcome)
        if blue_actor_id:
            conditions.append("AND r.blue_actor_id = ?")
            params.append(blue_actor_id)

        where_sql = " ".join(conditions)
        total = self._query_scalar(f"SELECT COUNT(*) {base_query} {where_sql}", params)
        order_sql = allowed_sorts.get(sort_by, allowed_sorts["run_id"])
        direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
        rows = self._query(
            f"""
            SELECT *
            {base_query}
            {where_sql}
            ORDER BY {order_sql} {direction}
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        return {"total": total, "limit": limit, "offset": offset, "items": rows}

    def get_run_detail(self, run_id: str) -> dict[str, Any]:
        run_dir = self.settings.runs_dir / run_id
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            raise ResourceNotFoundError(f"Run '{run_id}' was not found.")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        final_state = self._read_json_if_exists(run_dir / "final_state.json")
        aar = self._read_json_if_exists(run_dir / "aar.json")
        lessons = self._read_json_if_exists(run_dir / "lessons.json") or []
        instantiation = self._read_json_if_exists(run_dir / "instantiation.json")
        scenario = self._resolve_run_scenario(manifest, instantiation)
        events = self._load_events(run_dir)

        return {
            "manifest": manifest,
            "scenario": scenario,
            "final_state": final_state,
            "aar": aar,
            "lessons": lessons,
            "instantiation": instantiation,
            "event_summary": {
                "event_count": len(events),
                "by_phase": dict(Counter(event["phase"] for event in events)),
                "by_action_type": dict(Counter(event["action_type"] for event in events)),
                "max_turn": max((event["turn"] for event in events), default=0),
            },
        }

    def get_run_events(
        self,
        run_id: str,
        *,
        turn: int | None = None,
        phase: str | None = None,
        actor_side: str | None = None,
        action_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        run_dir = self.settings.runs_dir / run_id
        if not (run_dir / "event_log.jsonl").exists():
            raise ResourceNotFoundError(f"Run '{run_id}' was not found.")

        events = self._load_events(run_dir)
        filtered = [
            event
            for event in events
            if (turn is None or event["turn"] == turn)
            and (phase is None or event["phase"] == phase)
            and (actor_side is None or event["actor_side"] == actor_side)
            and (action_type is None or event["action_type"] == action_type)
        ]
        return {"total": len(filtered), "limit": limit, "offset": offset, "items": filtered[offset : offset + limit]}

    def list_comparisons(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
        total = self._query_scalar("SELECT COUNT(*) FROM comparisons")
        rows = self._query(
            f"""
            SELECT *
            FROM comparisons
            ORDER BY comparison_id {direction}
            LIMIT ? OFFSET ?
            """,
            [limit, offset],
        )
        return {"total": total, "limit": limit, "offset": offset, "items": rows}

    def get_comparison_detail(self, comparison_id: str) -> dict[str, Any]:
        comparison_dir = self.settings.runs_dir / comparison_id
        comparison_path = comparison_dir / "comparison.json"
        if not comparison_path.exists():
            raise ResourceNotFoundError(f"Comparison '{comparison_id}' was not found.")

        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        metric_rows = self._query(
            """
            SELECT *
            FROM comparison_metrics
            WHERE comparison_id = ?
            ORDER BY mean_overall_score DESC, coa_id ASC
            """,
            [comparison_id],
        )
        run_ids = {
            run_id
            for run_list in comparison.get("run_ids_by_coa", {}).values()
            for run_id in run_list
        }
        linked_runs: list[dict[str, Any]] = []
        if run_ids:
            placeholders = ", ".join(["?"] * len(run_ids))
            linked_runs = self._query(
                f"""
                SELECT *
                FROM run_with_quality
                WHERE run_id IN ({placeholders})
                ORDER BY run_id DESC
                """,
                list(run_ids),
            )
        return {"comparison": comparison, "metric_rows": metric_rows, "linked_runs": linked_runs}

    def get_instantiation_detail(self, instantiation_id: str) -> dict[str, Any]:
        instantiation_dir = self.settings.generated_dir / instantiation_id
        instantiation_path = instantiation_dir / "instantiation.json"
        if not instantiation_path.exists():
            raise ResourceNotFoundError(f"Instantiation '{instantiation_id}' was not found.")

        return {
            "instantiation": json.loads(instantiation_path.read_text(encoding="utf-8")),
            "scenario": json.loads((instantiation_dir / "scenario.json").read_text(encoding="utf-8")),
            "blue_force": json.loads((instantiation_dir / "blue_force.json").read_text(encoding="utf-8")),
            "red_force": json.loads((instantiation_dir / "red_force.json").read_text(encoding="utf-8")),
            "blue_coa": json.loads((instantiation_dir / "blue_coa.json").read_text(encoding="utf-8")),
            "red_coa": json.loads((instantiation_dir / "red_coa.json").read_text(encoding="utf-8")),
        }

    def list_lessons(
        self,
        *,
        tag: str | None = None,
        condition: str | None = None,
        scenario_id: str | None = None,
        run_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = self._query(
            """
            SELECT
              l.*,
              r.scenario_id,
              r.blue_actor_id,
              r.red_actor_id,
              r.final_outcome,
              r.quality_band
            FROM lessons l
            LEFT JOIN run_with_quality r ON l.run_id = r.run_id
            ORDER BY l.run_id DESC
            """
        )
        filtered = [
            row
            for row in rows
            if (tag is None or tag in (row.get("tags") or []))
            and (condition is None or condition in (row.get("conditions") or []))
            and (scenario_id is None or row.get("scenario_id") == scenario_id)
            and (run_id is None or row.get("run_id") == run_id)
        ]
        return {"total": len(filtered), "limit": limit, "offset": offset, "items": filtered[offset : offset + limit]}

    def resolve_template_paths(
        self,
        *,
        scenario_template_id: str,
        blue_force_template_id: str,
        red_force_template_id: str,
        blue_coa_template_ids: list[str],
        red_coa_template_id: str,
    ) -> dict[str, Any]:
        ids = [
            scenario_template_id,
            blue_force_template_id,
            red_force_template_id,
            red_coa_template_id,
            *blue_coa_template_ids,
        ]
        placeholders = ", ".join(["?"] * len(ids))
        rows = self._query(
            f"""
            SELECT template_id, template_path
            FROM templates
            WHERE template_id IN ({placeholders})
            """,
            ids,
        )
        path_by_id = {row["template_id"]: Path(row["template_path"]) for row in rows}
        missing = [template_id for template_id in ids if template_id not in path_by_id]
        if missing:
            raise ResourceNotFoundError(f"Template ids not found in catalog: {missing}")
        return {
            "scenario_template_path": path_by_id[scenario_template_id],
            "blue_force_template_path": path_by_id[blue_force_template_id],
            "red_force_template_path": path_by_id[red_force_template_id],
            "blue_coa_template_paths": [path_by_id[template_id] for template_id in blue_coa_template_ids],
            "red_coa_template_path": path_by_id[red_coa_template_id],
        }

    def _connect(self) -> duckdb.DuckDBPyConnection:
        if not self.settings.catalog_path.exists():
            raise CatalogUnavailableError(
                f"Catalog is missing at {self.settings.catalog_path}. Run `oeg build-catalog` first."
            )
        return duckdb.connect(str(self.settings.catalog_path), read_only=True)

    def _query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.execute(sql, params or [])
            columns = [column[0] for column in cursor.description]
            return [{column: value for column, value in zip(columns, row)} for row in cursor.fetchall()]
        finally:
            conn.close()

    def _query_one(self, sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def _query_scalar(self, sql: str, params: list[Any] | None = None) -> int:
        row = self._query_one(sql, params)
        if not row:
            return 0
        return int(next(iter(row.values())))

    def _list_recent_runs(self, limit: int) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT run_id, scenario_id, final_outcome, blue_overall_score, red_overall_score, quality_band
            FROM run_with_quality
            ORDER BY run_id DESC
            LIMIT ?
            """,
            [limit],
        )

    def _list_recent_comparisons(self, limit: int) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT comparison_id, scenario_id, recommended_coa, confidence, sample_count
            FROM comparisons
            ORDER BY comparison_id DESC
            LIMIT ?
            """,
            [limit],
        )

    def _list_recent_templates(self, limit: int) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT t.template_id, t.template_kind, t.name, q.approval_state, q.quality_score
            FROM templates t
            LEFT JOIN template_quality q ON t.template_id = q.template_id
            WHERE q.approval_state = 'approved_for_batch'
            ORDER BY COALESCE(q.quality_score, 0) DESC, t.template_id ASC
            LIMIT ?
            """,
            [limit],
        )

    def _related_runs_for_template(self, template_row: dict[str, Any]) -> list[dict[str, Any]]:
        template_id = template_row["template_id"]
        kind = template_row["template_kind"]
        if kind == "scenario_template":
            condition = "source_scenario_template_id = ?"
        elif kind == "force_template":
            condition = "(source_blue_force_template_id = ? OR source_red_force_template_id = ?)"
        else:
            condition = "(source_blue_coa_template_id = ? OR source_red_coa_template_id = ?)"
        params = [template_id] if kind == "scenario_template" else [template_id, template_id]
        return self._query(
            f"""
            SELECT run_id, scenario_id, final_outcome, blue_actor_id, red_actor_id, quality_band
            FROM run_with_quality
            WHERE {condition}
            ORDER BY run_id DESC
            LIMIT 10
            """,
            params,
        )

    def _related_comparisons_for_template(self, template_row: dict[str, Any]) -> list[dict[str, Any]]:
        kind = template_row["template_kind"]
        if kind == "scenario_template":
            return self._query(
                """
                SELECT comparison_id, scenario_id, recommended_coa, confidence, sample_count
                FROM comparisons
                WHERE scenario_id = ?
                ORDER BY comparison_id DESC
                LIMIT 10
                """,
                [template_row["base_asset_id"]],
            )
        if kind == "coa_template":
            return self._query(
                """
                SELECT DISTINCT c.comparison_id, c.scenario_id, c.recommended_coa, c.confidence, c.sample_count
                FROM comparisons c
                LEFT JOIN comparison_metrics m ON c.comparison_id = m.comparison_id
                WHERE m.coa_id = ? OR c.red_coa_id = ?
                ORDER BY c.comparison_id DESC
                LIMIT 10
                """,
                [template_row["base_asset_id"], template_row["base_asset_id"]],
            )
        return []

    def _resolve_run_scenario(
        self,
        manifest: dict[str, Any],
        instantiation: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if instantiation and manifest.get("source_scenario_template_id"):
            template_detail = self.get_template_detail(manifest["source_scenario_template_id"])
            scenario = template_detail["raw_template"]["base_scenario"]
            sampled = instantiation.get("sampled_values", {}).get("scenario", {})
            if "weather" in sampled:
                scenario["environment"]["weather"] = sampled["weather"]
            if "visibility" in sampled:
                scenario["environment"]["visibility"] = sampled["visibility"]
            for zone in scenario.get("zones", []):
                zone["strategic_value"] = sampled.get("zone_strategic_values", {}).get(zone["id"], zone["strategic_value"])
            return scenario

        scenario_path = self.settings.project_root / "data" / "scenarios" / f"{manifest['scenario_id']}.json"
        if scenario_path.exists():
            return json.loads(scenario_path.read_text(encoding="utf-8"))
        return None

    def _read_json_if_exists(self, path: Path) -> dict[str, Any] | list[dict[str, Any]] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_events(self, run_dir: Path) -> list[dict[str, Any]]:
        path = run_dir / "event_log.jsonl"
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
