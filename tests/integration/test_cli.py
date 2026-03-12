from __future__ import annotations

import json

import duckdb
from typer.testing import CliRunner

import oeg.cli as cli_module
from oeg.cli import app
from oeg.paths import sample_scenario_path


runner = CliRunner()


def test_validate_assets_command_passes() -> None:
    result = runner.invoke(app, ["validate-assets"])
    assert result.exit_code == 0, result.stdout
    assert "Validation passed" in result.stdout


def test_run_scenario_command_writes_bundle(tmp_path) -> None:
    result = runner.invoke(
        app,
        ["run-scenario", "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.stdout

    run_dirs = [item for item in tmp_path.iterdir() if item.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    aar = json.loads((run_dir / "aar.json").read_text(encoding="utf-8"))
    assert manifest["scenario_id"] == "scn_corridor_001"
    assert manifest["blue_coa_id"] == "blue_delay_center"
    assert aar["run_id"] == manifest["id"]
    assert (run_dir / "event_log.jsonl").exists()
    assert (run_dir / "turn_states.jsonl").exists()


def test_compare_coas_command_writes_comparison(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "compare-coas",
            "--seed",
            "11",
            "--seed",
            "22",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.stdout

    comparison_dirs = [item for item in tmp_path.iterdir() if item.is_dir() and item.name.startswith("comparison_")]
    assert len(comparison_dirs) == 1
    comparison = json.loads((comparison_dirs[0] / "comparison.json").read_text(encoding="utf-8"))
    assert comparison["scenario_id"] == "scn_corridor_001"
    assert comparison["sample_count"] == 2
    assert len(comparison["coa_ids"]) == 2
    assert comparison["recommended_coa"] in set(comparison["coa_ids"])


def test_run_runtime_demo_command_writes_bundle(tmp_path) -> None:
    result = runner.invoke(
        app,
        ["run-runtime-demo", "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.stdout

    run_dirs = [item for item in tmp_path.iterdir() if item.is_dir()]
    assert len(run_dirs) == 1
    manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    final_state = json.loads((run_dirs[0] / "final_state.json").read_text(encoding="utf-8"))
    assert manifest["blue_coa_id"] == "blue_heuristic"
    assert manifest["red_coa_id"] == "red_heuristic"
    blue_view = final_state["side_views"]["blue"]
    assert "suspected_enemy_zones" in blue_view
    assert "false_contact_zones" in blue_view
    assert "zone_confidence" in blue_view


def test_replay_generation_batch_command_promotes_asset(tmp_path) -> None:
    request_file = tmp_path / "requests.json"
    replay_file = tmp_path / "replay.json"
    template_file = tmp_path / "scenario_prompt.md"
    template_file.write_text("Generate scenario for {scenario_family}.", encoding="utf-8")
    request_file.write_text(
        json.dumps(
            [
                {
                    "request_id": "scenario_batch",
                    "asset_kind": "scenario",
                    "template_path": str(template_file),
                    "count": 1,
                    "context": {"scenario_family": "corridor_delay"}
                }
            ]
        ),
        encoding="utf-8",
    )
    replay_file.write_text(
        json.dumps({"scenario_batch": sample_scenario_path().read_text(encoding="utf-8")}),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "replay-generation-batch",
            "--request-file",
            str(request_file),
            "--replay-file",
            str(replay_file),
            "--output-dir",
            str(tmp_path / "generated"),
        ],
    )
    assert result.exit_code == 0, result.stdout

    batch_dirs = [item for item in (tmp_path / "generated").iterdir() if item.is_dir()]
    assert len(batch_dirs) == 1
    manifest = json.loads((batch_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["promoted_count"] == 1


def test_generate_live_batch_command_promotes_asset_with_fake_provider(tmp_path, monkeypatch) -> None:
    request_file = tmp_path / "requests.json"
    template_file = tmp_path / "scenario_prompt.md"
    template_file.write_text("Generate scenario for {scenario_family}.", encoding="utf-8")
    request_file.write_text(
        json.dumps(
            [
                {
                    "request_id": "scenario_batch",
                    "asset_kind": "scenario",
                    "template_path": str(template_file),
                    "count": 1,
                    "context": {"scenario_family": "corridor_delay"}
                }
            ]
        ),
        encoding="utf-8",
    )

    class FakeLiveProvider:
        def __init__(self, **_: object) -> None:
            self._payload = sample_scenario_path().read_text(encoding="utf-8")

        def generate(self, prompt: str, request, iteration: int) -> str:
            del prompt, request, iteration
            return self._payload

    monkeypatch.setattr(cli_module, "OpenAIResponsesGenerationProvider", FakeLiveProvider)

    result = runner.invoke(
        app,
        [
            "generate-live-batch",
            "--request-file",
            str(request_file),
            "--output-dir",
            str(tmp_path / "generated"),
        ],
    )
    assert result.exit_code == 0, result.stdout

    batch_dirs = [item for item in (tmp_path / "generated").iterdir() if item.is_dir()]
    assert len(batch_dirs) == 1
    manifest = json.loads((batch_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["promoted_count"] == 1


def test_instantiate_assets_command_writes_concrete_bundle(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "instantiate-assets",
            "--output-dir",
            str(tmp_path),
            "--seed",
            "19",
        ],
    )
    assert result.exit_code == 0, result.stdout

    instantiation_dirs = [item for item in tmp_path.iterdir() if item.is_dir()]
    assert len(instantiation_dirs) == 1
    instantiation = json.loads((instantiation_dirs[0] / "instantiation.json").read_text(encoding="utf-8"))
    scenario = json.loads((instantiation_dirs[0] / "scenario.json").read_text(encoding="utf-8"))
    assert instantiation["stochastic_profile_id"] == "hybrid_stochastic_v1"
    assert scenario["id"] == "scn_corridor_001"
    assert (instantiation_dirs[0] / "blue_force.json").exists()
    assert (instantiation_dirs[0] / "blue_coa.json").exists()


def test_run_batch_command_writes_runs_and_comparison(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "run-batch",
            "--seed",
            "11",
            "--seed",
            "22",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.stdout

    run_dirs = [item for item in tmp_path.iterdir() if item.is_dir() and item.name.startswith("run_")]
    comparison_dirs = [item for item in tmp_path.iterdir() if item.is_dir() and item.name.startswith("comparison_")]
    assert len(run_dirs) == 4
    assert len(comparison_dirs) == 1

    manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    instantiation = json.loads((run_dirs[0] / "instantiation.json").read_text(encoding="utf-8"))
    comparison = json.loads((comparison_dirs[0] / "comparison.json").read_text(encoding="utf-8"))
    assert manifest["instantiation_id"] == instantiation["id"]
    assert manifest["source_blue_coa_template_id"] is not None
    assert comparison["sample_count"] == 2


def test_run_batch_command_rejects_unapproved_templates(tmp_path) -> None:
    from shutil import copytree

    templates_dir = tmp_path / "templates"
    catalog_path = tmp_path / "catalog.duckdb"
    copytree("data/templates", templates_dir)

    conn = duckdb.connect(str(catalog_path))
    try:
        conn.execute(
            "CREATE TABLE template_quality AS SELECT * FROM (VALUES "
            "('some_other_template', 'scenario_template', 'approved_for_batch')"
            ") AS t(template_id, template_kind, approval_state)"
        )
        conn.execute(
            "CREATE VIEW approved_templates AS "
            "SELECT template_kind, template_id FROM template_quality WHERE approval_state = 'approved_for_batch'"
        )
    finally:
        conn.close()

    result = runner.invoke(
        app,
        [
            "run-batch",
            "--output-dir",
            str(tmp_path / "runs"),
            "--catalog-path",
            str(catalog_path),
            "--scenario-template",
            str(templates_dir / "scenarios" / "scn_corridor_template_001.json"),
            "--blue-force-template",
            str(templates_dir / "force_packages" / "fp_blue_template_001.json"),
            "--red-force-template",
            str(templates_dir / "force_packages" / "fp_red_template_001.json"),
            "--blue-coa-template",
            str(templates_dir / "coas" / "blue_delay_center_template.json"),
            "--blue-coa-template",
            str(templates_dir / "coas" / "blue_mobile_flank_template.json"),
            "--red-coa-template",
            str(templates_dir / "coas" / "red_direct_thrust_template.json"),
        ],
    )
    assert result.exit_code == 1
    assert "requires catalog-approved templates" in result.stdout


def test_export_dataset_command_writes_flat_tables(tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    datasets_dir = tmp_path / "datasets"

    run_result = runner.invoke(
        app,
        ["run-scenario", "--output-dir", str(runs_dir)],
    )
    assert run_result.exit_code == 0, run_result.stdout

    export_result = runner.invoke(
        app,
        ["export-dataset", "--runs-dir", str(runs_dir), "--output-dir", str(datasets_dir)],
    )
    assert export_result.exit_code == 0, export_result.stdout

    manifest = json.loads((datasets_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_count"] == 1
    assert manifest["event_count"] > 0
    assert (datasets_dir / "run_manifest_rows.jsonl").exists()
    assert (datasets_dir / "event_rows.jsonl").exists()


def test_aggregate_lessons_command_writes_clusters(tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    analysis_dir = tmp_path / "analysis"

    run_result = runner.invoke(
        app,
        ["compare-coas", "--seed", "11", "--seed", "22", "--output-dir", str(runs_dir)],
    )
    assert run_result.exit_code == 0, run_result.stdout

    aggregate_result = runner.invoke(
        app,
        ["aggregate-lessons", "--runs-dir", str(runs_dir), "--output-dir", str(analysis_dir)],
    )
    assert aggregate_result.exit_code == 0, aggregate_result.stdout

    manifest = json.loads((analysis_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_count"] >= 1
    assert manifest["cluster_count"] >= 1
    assert (analysis_dir / "lesson_clusters.jsonl").exists()


def test_evaluate_runs_command_writes_quality_rows(tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    analysis_dir = tmp_path / "quality"

    run_result = runner.invoke(
        app,
        ["run-runtime-demo", "--output-dir", str(runs_dir)],
    )
    assert run_result.exit_code == 0, run_result.stdout

    evaluate_result = runner.invoke(
        app,
        ["evaluate-runs", "--runs-dir", str(runs_dir), "--output-dir", str(analysis_dir)],
    )
    assert evaluate_result.exit_code == 0, evaluate_result.stdout

    manifest = json.loads((analysis_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_count"] == 1
    assert (analysis_dir / "run_quality_rows.jsonl").exists()


def test_evaluate_templates_command_writes_template_quality_rows(tmp_path) -> None:
    from shutil import copytree

    templates_dir = tmp_path / "templates"
    analysis_dir = tmp_path / "template_analysis"
    copytree("data/templates", templates_dir)

    result = runner.invoke(
        app,
        ["evaluate-templates", "--templates-dir", str(templates_dir), "--output-dir", str(analysis_dir)],
    )
    assert result.exit_code == 0, result.stdout

    manifest = json.loads((analysis_dir / "template_manifest.json").read_text(encoding="utf-8"))
    approval_manifest = json.loads((analysis_dir / "template_approval_manifest.json").read_text(encoding="utf-8"))
    assert manifest["template_count"] == 6
    assert "approved_for_batch" in approval_manifest
    assert (analysis_dir / "template_quality_rows.jsonl").exists()


def test_build_catalog_command_writes_duckdb_catalog(tmp_path) -> None:
    from shutil import copytree

    templates_dir = tmp_path / "templates"
    runs_dir = tmp_path / "runs"
    datasets_dir = tmp_path / "datasets"
    analysis_dir = tmp_path / "analysis"
    catalog_path = tmp_path / "catalog.duckdb"
    copytree("data/templates", templates_dir)

    run_result = runner.invoke(
        app,
        [
            "run-batch",
            "--seed",
            "11",
            "--seed",
            "22",
            "--output-dir",
            str(runs_dir),
            "--scenario-template",
            str(templates_dir / "scenarios" / "scn_corridor_template_001.json"),
            "--blue-force-template",
            str(templates_dir / "force_packages" / "fp_blue_template_001.json"),
            "--red-force-template",
            str(templates_dir / "force_packages" / "fp_red_template_001.json"),
            "--blue-coa-template",
            str(templates_dir / "coas" / "blue_delay_center_template.json"),
            "--blue-coa-template",
            str(templates_dir / "coas" / "blue_mobile_flank_template.json"),
            "--red-coa-template",
            str(templates_dir / "coas" / "red_direct_thrust_template.json"),
        ],
    )
    assert run_result.exit_code == 0, run_result.stdout

    catalog_result = runner.invoke(
        app,
        [
            "build-catalog",
            "--runs-dir",
            str(runs_dir),
            "--templates-dir",
            str(templates_dir),
            "--datasets-dir",
            str(datasets_dir),
            "--analysis-dir",
            str(analysis_dir),
            "--output-path",
            str(catalog_path),
        ],
    )
    assert catalog_result.exit_code == 0, catalog_result.stdout
    assert catalog_path.exists()

    conn = duckdb.connect(str(catalog_path))
    try:
        run_count = conn.execute("SELECT COUNT(*) FROM run_manifests").fetchone()[0]
        template_count = conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
        comparison_count = conn.execute("SELECT COUNT(*) FROM comparisons").fetchone()[0]
    finally:
        conn.close()

    assert run_count == 4
    assert template_count == 6
    assert comparison_count == 1
