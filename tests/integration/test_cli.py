from __future__ import annotations

import json
from pathlib import Path

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
