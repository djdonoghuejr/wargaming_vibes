from __future__ import annotations

import json
from shutil import copytree

from oeg.evaluation.quality import evaluate_templates


def test_evaluate_templates_scores_sample_library(tmp_path) -> None:
    templates_dir = tmp_path / "templates"
    output_dir = tmp_path / "analysis"

    copytree("data/templates", templates_dir)

    manifest = evaluate_templates(templates_dir, output_dir)

    assert manifest["template_count"] == 6
    assert manifest["approved_for_batch_count"] >= 1
    approval_manifest = json.loads((output_dir / "template_approval_manifest.json").read_text(encoding="utf-8"))
    assert "scn_corridor_template_001" in approval_manifest["approved_for_batch"]
    assert (output_dir / "template_quality_rows.jsonl").exists()


def test_evaluate_templates_quarantines_unparseable_template(tmp_path) -> None:
    templates_dir = tmp_path / "templates"
    (templates_dir / "scenarios").mkdir(parents=True, exist_ok=True)
    (templates_dir / "force_packages").mkdir(parents=True, exist_ok=True)
    (templates_dir / "coas").mkdir(parents=True, exist_ok=True)
    (templates_dir / "scenarios" / "bad_template.json").write_text("{bad json", encoding="utf-8")

    output_dir = tmp_path / "analysis"
    manifest = evaluate_templates(templates_dir, output_dir)

    assert manifest["quarantined_count"] == 1
    rows = (output_dir / "template_quality_rows.jsonl").read_text(encoding="utf-8").splitlines()
    assert any("bad_template" in row and "quarantined" in row for row in rows)
