from __future__ import annotations

import json
from pathlib import Path

from oeg.generators import AssetKind
from oeg.generators import GenerationRequest
from oeg.generators import OfflineGenerationPipeline
from oeg.generators import StaticGenerationProvider
from oeg.paths import sample_blue_force_path
from oeg.paths import sample_scenario_path


def test_offline_generation_pipeline_promotes_valid_scenario(tmp_path) -> None:
    template_path = tmp_path / "scenario_prompt.md"
    template_path.write_text(
        "Generate scenario for {scenario_family} iteration {iteration}.",
        encoding="utf-8",
    )
    raw_scenario = sample_scenario_path().read_text(encoding="utf-8")
    request = GenerationRequest(
        request_id="scenario_batch",
        asset_kind=AssetKind.SCENARIO,
        template_path=str(template_path),
        count=1,
        context={"scenario_family": "corridor_delay"},
    )
    provider = StaticGenerationProvider({"scenario_batch": raw_scenario})
    pipeline = OfflineGenerationPipeline(tmp_path / "generated")

    result = pipeline.run_batch([request], provider)

    assert result.promoted_count == 1
    assert result.quarantined_count == 0
    promoted_record = result.records[0]
    promoted_payload = json.loads(Path(promoted_record.result_path).read_text(encoding="utf-8"))
    assert promoted_payload["id"] == "scn_corridor_001"


def test_offline_generation_pipeline_quarantines_invalid_coa(tmp_path) -> None:
    template_path = tmp_path / "coa_prompt.md"
    template_path.write_text(
        "Generate COA for {side}.",
        encoding="utf-8",
    )
    invalid_coa = {
        "id": "bad_coa",
        "schema_version": "0.1.0",
        "side": "blue",
        "name": "Broken COA",
        "description": "Contains an invalid unit id.",
        "strategy_tags": ["test"],
        "actions": [
            {
                "turn": 1,
                "unit_id": "missing_unit",
                "action": "attack",
                "target_zone": "CITY"
            }
        ]
    }
    request = GenerationRequest(
        request_id="coa_batch",
        asset_kind=AssetKind.COA,
        template_path=str(template_path),
        context={"side": "blue"},
        validation_context={
            "scenario_path": str(sample_scenario_path()),
            "force_package_path": str(sample_blue_force_path()),
        },
    )
    provider = StaticGenerationProvider({"coa_batch": json.dumps(invalid_coa)})
    pipeline = OfflineGenerationPipeline(tmp_path / "generated")

    result = pipeline.run_batch([request], provider)

    assert result.promoted_count == 0
    assert result.quarantined_count == 1
    quarantined_record = result.records[0]
    quarantined_payload = json.loads(Path(quarantined_record.result_path).read_text(encoding="utf-8"))
    assert "unknown unit" in quarantined_payload["errors"][0].lower()
