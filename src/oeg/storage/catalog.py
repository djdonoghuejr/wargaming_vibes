from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import duckdb

from oeg.evaluation.quality import evaluate_runs
from oeg.evaluation.quality import evaluate_templates
from oeg.storage.export import export_run_dataset
from oeg.storage.io import ensure_directory
from oeg.storage.io import write_json
from oeg.storage.io import write_jsonl


def build_duckdb_catalog(
    runs_dir: str | Path,
    templates_dir: str | Path,
    datasets_dir: str | Path,
    analysis_dir: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    runs_root = Path(runs_dir)
    templates_root = Path(templates_dir)
    datasets_root = ensure_directory(Path(datasets_dir))
    analysis_root = ensure_directory(Path(analysis_dir))
    catalog_path = Path(output_path)
    ensure_directory(catalog_path.parent)

    dataset_manifest = export_run_dataset(runs_root, datasets_root)
    run_quality_manifest = evaluate_runs(runs_root, analysis_root)
    template_quality_manifest = evaluate_templates(templates_root, analysis_root)

    template_rows = _collect_template_rows(templates_root)
    comparison_rows, comparison_metric_rows = _collect_comparison_rows(runs_root)

    with TemporaryDirectory() as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        template_rows_path = write_jsonl(tmp_dir / "template_rows.jsonl", template_rows)
        comparison_rows_path = write_jsonl(tmp_dir / "comparison_rows.jsonl", comparison_rows)
        comparison_metric_rows_path = write_jsonl(
            tmp_dir / "comparison_metric_rows.jsonl",
            comparison_metric_rows,
        )

        conn = duckdb.connect(str(catalog_path))
        try:
            _create_table_from_jsonl(
                conn,
                "run_manifests",
                datasets_root / "run_manifest_rows.jsonl",
            )
            _create_table_from_jsonl(conn, "aars", datasets_root / "aar_rows.jsonl")
            _create_table_from_jsonl(conn, "lessons", datasets_root / "lesson_rows.jsonl")
            _create_table_from_jsonl(conn, "events", datasets_root / "event_rows.jsonl")
            _create_table_from_jsonl(
                conn,
                "instantiations",
                datasets_root / "instantiation_rows.jsonl",
            )
            _create_table_from_jsonl(
                conn,
                "run_quality",
                analysis_root / "run_quality_rows.jsonl",
            )
            _create_table_from_jsonl(
                conn,
                "template_quality",
                analysis_root / "template_quality_rows.jsonl",
            )
            _create_table_from_jsonl(conn, "templates", template_rows_path)
            _create_table_from_jsonl(conn, "comparisons", comparison_rows_path)
            _create_table_from_jsonl(
                conn,
                "comparison_metrics",
                comparison_metric_rows_path,
            )
            conn.execute("CREATE OR REPLACE VIEW approved_templates AS SELECT * FROM template_quality WHERE approval_state = 'approved_for_batch'")
            conn.execute(
                "CREATE OR REPLACE VIEW run_with_quality AS "
                "SELECT r.*, q.quality_score, q.quality_band "
                "FROM run_manifests r LEFT JOIN run_quality q ON r.run_id = q.run_id"
            )
            table_counts = {
                table_name: conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                for table_name in (
                    "templates",
                    "template_quality",
                    "run_manifests",
                    "instantiations",
                    "aars",
                    "lessons",
                    "events",
                    "run_quality",
                    "comparisons",
                    "comparison_metrics",
                )
            }
        finally:
            conn.close()

    manifest = {
        "catalog_path": str(catalog_path),
        "source_runs_dir": str(runs_root),
        "source_templates_dir": str(templates_root),
        "datasets_dir": str(datasets_root),
        "analysis_dir": str(analysis_root),
        "dataset_manifest": dataset_manifest,
        "run_quality_manifest": run_quality_manifest,
        "template_quality_manifest": template_quality_manifest,
        "table_counts": table_counts,
    }
    write_json(catalog_path.with_suffix(".manifest.json"), manifest)
    return manifest


def load_approved_template_index(catalog_path: str | Path) -> dict[str, set[str]]:
    path = Path(catalog_path)
    if not path.exists():
        raise FileNotFoundError(
            f"DuckDB catalog not found at {path}. Build the catalog before running approval-gated batches."
        )

    conn = duckdb.connect(str(path), read_only=True)
    try:
        rows = conn.execute(
            "SELECT template_kind, template_id FROM approved_templates"
        ).fetchall()
    except duckdb.Error as exc:
        raise RuntimeError(
            f"Catalog at {path} does not expose approved_templates. Rebuild the catalog and try again."
        ) from exc
    finally:
        conn.close()

    approved: dict[str, set[str]] = {}
    for template_kind, template_id in rows:
        approved.setdefault(str(template_kind), set()).add(str(template_id))
    return approved


def _create_table_from_jsonl(conn: duckdb.DuckDBPyConnection, table_name: str, path: Path) -> None:
    if not path.exists():
        conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT NULL WHERE FALSE")
        return
    conn.execute(
        f"CREATE OR REPLACE TABLE {table_name} AS "
        "SELECT * FROM read_json_auto(?, format='newline_delimited', ignore_errors=true)",
        [str(path)],
    )


def _collect_template_rows(templates_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for template_kind, subdir in (
        ("scenario_template", "scenarios"),
        ("force_template", "force_packages"),
        ("coa_template", "coas"),
    ):
        root = templates_dir / subdir
        if not root.exists():
            continue
        for path in sorted(item for item in root.iterdir() if item.is_file() and item.suffix == ".json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                rows.append(
                    {
                        "template_id": path.stem,
                        "template_kind": template_kind,
                        "template_path": str(path),
                        "parse_status": "invalid_json",
                    }
                )
                continue

            row = {
                "template_id": payload.get("id", path.stem),
                "template_kind": template_kind,
                "template_path": str(path),
                "name": payload.get("name"),
                "description": payload.get("description"),
                "schema_version": payload.get("schema_version"),
                "parse_status": "ok",
            }
            if template_kind == "scenario_template":
                base = payload.get("base_scenario", {})
                row.update(
                    {
                        "base_asset_id": base.get("id"),
                        "weather_option_count": len(payload.get("weather_options", [])),
                        "visibility_option_count": len(payload.get("visibility_options", [])),
                        "zone_adjustment_count": len(payload.get("zone_strategic_value_adjustments", {})),
                    }
                )
            elif template_kind == "force_template":
                base = payload.get("base_force", {})
                row.update(
                    {
                        "base_asset_id": base.get("id"),
                        "side": payload.get("side"),
                        "doctrine": payload.get("doctrine"),
                        "unit_variability_count": len(payload.get("unit_variability", [])),
                    }
                )
            else:
                base = payload.get("base_coa", {})
                row.update(
                    {
                        "base_asset_id": base.get("id"),
                        "side": payload.get("side"),
                        "strategy_tags": payload.get("strategy_tags", []),
                        "action_variation_count": len(payload.get("action_variations", [])),
                    }
                )
            rows.append(row)
    return rows


def _collect_comparison_rows(runs_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    comparison_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    for comparison_dir in sorted(
        item for item in runs_dir.iterdir() if item.is_dir() and item.name.startswith("comparison_")
    ):
        comparison_path = comparison_dir / "comparison.json"
        if not comparison_path.exists():
            continue
        payload = json.loads(comparison_path.read_text(encoding="utf-8"))
        comparison_rows.append(
            {
                "comparison_id": payload["id"],
                "scenario_id": payload["scenario_id"],
                "red_coa_id": payload["red_coa_id"],
                "sample_count": payload["sample_count"],
                "recommended_coa": payload["recommended_coa"],
                "score_delta": payload.get("paired_seed_stats", {}).get("score_delta"),
                "objective_delta": payload.get("paired_seed_stats", {}).get("objective_delta"),
                "casualty_delta": payload.get("paired_seed_stats", {}).get("casualty_delta"),
                "confidence": payload.get("paired_seed_stats", {}).get("confidence"),
                "coa_ids": payload.get("coa_ids", []),
                "seed_list": payload.get("seed_list", []),
                "tradeoffs": payload.get("tradeoffs"),
            }
        )
        for coa_id, metrics in payload.get("metric_results", {}).items():
            metric_rows.append(
                {
                    "comparison_id": payload["id"],
                    "scenario_id": payload["scenario_id"],
                    "coa_id": coa_id,
                    "mean_overall_score": metrics.get("mean_overall_score"),
                    "mean_objective_control": metrics.get("mean_objective_control"),
                    "mean_force_preservation": metrics.get("mean_force_preservation"),
                    "mean_sustainment": metrics.get("mean_sustainment"),
                    "mean_tempo": metrics.get("mean_tempo"),
                    "casualty_index": metrics.get("casualty_index"),
                }
            )
    return comparison_rows, metric_rows
