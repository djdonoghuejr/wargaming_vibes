from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.service import ApiSettings
from oeg.paths import default_runs_dir
from oeg.paths import project_root
from oeg.paths import template_dir
from oeg.storage.catalog import build_duckdb_catalog


def _build_test_client(tmp_path: Path) -> TestClient:
    root = project_root()
    runs_dir = tmp_path / "runs"
    templates_dir = tmp_path / "templates"
    analysis_dir = tmp_path / "analysis"
    datasets_dir = tmp_path / "datasets"
    generated_dir = tmp_path / "generated"
    catalog_path = tmp_path / "catalog.duckdb"

    shutil.copytree(default_runs_dir(), runs_dir)
    shutil.copytree(template_dir(), templates_dir)

    build_duckdb_catalog(
        runs_dir=runs_dir,
        templates_dir=templates_dir,
        datasets_dir=datasets_dir,
        analysis_dir=analysis_dir,
        output_path=catalog_path,
    )
    settings = ApiSettings(
        project_root=root,
        catalog_path=catalog_path,
        runs_dir=runs_dir,
        templates_dir=templates_dir,
        analysis_dir=analysis_dir,
        generated_dir=generated_dir,
    )
    return TestClient(create_app(settings))


def _poll_job(client: TestClient, job_id: str, timeout_seconds: float = 10.0) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = client.get(f"/actions/jobs/{job_id}")
        response.raise_for_status()
        payload = response.json()
        if payload["status"] in {"succeeded", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not complete within {timeout_seconds} seconds.")


def test_health_and_summary(tmp_path: Path) -> None:
    client = _build_test_client(tmp_path)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["catalog_exists"] is True

    summary = client.get("/catalog/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["counts"]["templates"] >= 5
    assert payload["counts"]["runs"] >= 1
    assert payload["recent_comparisons"]


def test_templates_runs_and_comparisons(tmp_path: Path) -> None:
    client = _build_test_client(tmp_path)

    templates = client.get(
        "/templates",
        params={"template_kind": "coa_template", "approval_state": "approved_for_batch"},
    )
    assert templates.status_code == 200
    template_items = templates.json()["items"]
    assert template_items
    first_template_id = template_items[0]["template_id"]

    template_detail = client.get(f"/templates/{first_template_id}")
    assert template_detail.status_code == 200
    assert template_detail.json()["summary"]["template_id"] == first_template_id

    runs = client.get(
        "/runs",
        params={"quality_band": "strong", "source_template_id": "blue_delay_center_template"},
    )
    assert runs.status_code == 200
    run_items = runs.json()["items"]
    assert run_items
    run_id = run_items[0]["run_id"]

    run_detail = client.get(f"/runs/{run_id}")
    assert run_detail.status_code == 200
    run_payload = run_detail.json()
    assert run_payload["manifest"]["id"] == run_id
    assert run_payload["aar"]["run_id"] == run_id
    assert "event_count" in run_payload["event_summary"]

    events = client.get(f"/runs/{run_id}/events", params={"phase": "engagement", "limit": 5})
    assert events.status_code == 200
    assert events.json()["total"] >= 1

    comparisons = client.get("/comparisons")
    assert comparisons.status_code == 200
    comparison_id = comparisons.json()["items"][0]["comparison_id"]

    comparison_detail = client.get(f"/comparisons/{comparison_id}")
    assert comparison_detail.status_code == 200
    comparison_payload = comparison_detail.json()
    assert comparison_payload["comparison"]["id"] == comparison_id
    assert comparison_payload["metric_rows"]

    lessons = client.get("/lessons", params={"tag": "ISR"})
    assert lessons.status_code == 200
    assert lessons.json()["items"]


def test_actions_and_job_status(tmp_path: Path) -> None:
    client = _build_test_client(tmp_path)

    instantiate = client.post(
        "/actions/instantiate",
        json={
            "scenario_template_id": "scn_corridor_template_001",
            "blue_force_template_id": "fp_blue_template_001",
            "red_force_template_id": "fp_red_template_001",
            "blue_coa_template_id": "blue_delay_center_template",
            "red_coa_template_id": "red_direct_thrust_template",
            "seed": 7,
            "sampling_profile": "hybrid_stochastic_v1",
        },
    )
    assert instantiate.status_code == 200
    instantiate_job = _poll_job(client, instantiate.json()["job_id"])
    assert instantiate_job["status"] == "succeeded"
    assert instantiate_job["result"]["instantiation_id"].startswith("instantiation_")

    instantiation_detail = client.get(
        f"/instantiations/{instantiate_job['result']['instantiation_id']}"
    )
    assert instantiation_detail.status_code == 200
    assert instantiation_detail.json()["instantiation"]["id"] == instantiate_job["result"]["instantiation_id"]

    run_batch = client.post(
        "/actions/run-batch",
        json={
            "scenario_template_id": "scn_corridor_template_001",
            "blue_force_template_id": "fp_blue_template_001",
            "red_force_template_id": "fp_red_template_001",
            "blue_coa_template_ids": [
                "blue_delay_center_template",
                "blue_mobile_flank_template",
            ],
            "red_coa_template_id": "red_direct_thrust_template",
            "seeds": [101, 202],
            "sampling_profile": "hybrid_stochastic_v1",
            "require_approved": True,
        },
    )
    assert run_batch.status_code == 200
    batch_job = _poll_job(client, run_batch.json()["job_id"])
    assert batch_job["status"] == "succeeded"
    assert batch_job["result"]["comparison_id"].startswith("comparison_")
    assert len(batch_job["result"]["run_ids"]) == 4


def test_action_rejects_unapproved_templates(tmp_path: Path) -> None:
    rogue_template = tmp_path / "templates" / "coas" / "rogue_template.json"
    runs_dir = tmp_path / "runs"
    templates_dir = tmp_path / "templates"
    analysis_dir = tmp_path / "analysis"
    datasets_dir = tmp_path / "datasets"
    generated_dir = tmp_path / "generated"
    catalog_path = tmp_path / "catalog.duckdb"

    shutil.copytree(default_runs_dir(), runs_dir)
    shutil.copytree(template_dir(), templates_dir)

    source = templates_dir / "coas" / "blue_delay_center_template.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["id"] = "rogue_template"
    payload["action_variations"] = []
    rogue_template.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    build_duckdb_catalog(
        runs_dir=runs_dir,
        templates_dir=templates_dir,
        datasets_dir=datasets_dir,
        analysis_dir=analysis_dir,
        output_path=catalog_path,
    )
    client = TestClient(
        create_app(
            ApiSettings(
                project_root=project_root(),
                catalog_path=catalog_path,
                runs_dir=runs_dir,
                templates_dir=templates_dir,
                analysis_dir=analysis_dir,
                generated_dir=generated_dir,
            )
        )
    )

    response = client.post(
        "/actions/run-batch",
        json={
            "scenario_template_id": "scn_corridor_template_001",
            "blue_force_template_id": "fp_blue_template_001",
            "red_force_template_id": "fp_red_template_001",
            "blue_coa_template_ids": ["rogue_template"],
            "red_coa_template_id": "red_direct_thrust_template",
            "seeds": [11],
            "sampling_profile": "hybrid_stochastic_v1",
            "require_approved": True,
        },
    )
    assert response.status_code == 200
    job = _poll_job(client, response.json()["job_id"])
    assert job["status"] == "failed"
    assert "Missing approvals" in job["error"]
