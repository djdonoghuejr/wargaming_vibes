from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from oeg.generators.models import AssetKind
from oeg.generators.models import GenerationBatchResult
from oeg.generators.models import GenerationRecord
from oeg.generators.models import GenerationRequest
from oeg.generators.models import GenerationStatus
from oeg.generators.provider import GenerationProvider
from oeg.schemas.models import COA
from oeg.schemas.models import ForcePackage
from oeg.schemas.models import Scenario
from oeg.storage.io import load_model
from oeg.storage.io import timestamp_id
from oeg.storage.io import write_json
from oeg.storage.io import write_jsonl
from oeg.validation.semantic import SemanticValidationError
from oeg.validation.semantic import validate_coa_semantics
from oeg.validation.semantic import validate_force_package_semantics
from oeg.validation.semantic import validate_scenario_semantics


MODEL_BY_KIND = {
    AssetKind.SCENARIO: Scenario,
    AssetKind.FORCE_PACKAGE: ForcePackage,
    AssetKind.COA: COA,
}

SUBDIR_BY_KIND = {
    AssetKind.SCENARIO: "scenarios",
    AssetKind.FORCE_PACKAGE: "force_packages",
    AssetKind.COA: "coas",
}


class OfflineGenerationPipeline:
    def __init__(self, output_root: str | Path) -> None:
        self.output_root = Path(output_root)

    def run_batch(
        self,
        requests: list[GenerationRequest],
        provider: GenerationProvider,
    ) -> GenerationBatchResult:
        batch_id = timestamp_id("generation")
        batch_dir = self.output_root / batch_id
        raw_dir = batch_dir / "raw"
        promoted_dir = batch_dir / "promoted"
        quarantine_dir = batch_dir / "quarantine"
        records: list[GenerationRecord] = []

        for request in requests:
            template = Path(request.template_path).read_text(encoding="utf-8")
            for iteration in range(1, request.count + 1):
                item_key = f"{request.request_id}_{iteration:02d}"
                prompt_path = raw_dir / f"{item_key}_prompt.md"
                response_path = raw_dir / f"{item_key}_response.txt"
                prompt_payload_path = prompt_path.with_suffix(".json")
                raw_response = ""

                try:
                    prompt = self._render_prompt(template, request, iteration)
                    write_json(prompt_payload_path, {"prompt": prompt})
                    raw_response = provider.generate(prompt=prompt, request=request, iteration=iteration)
                    response_path.parent.mkdir(parents=True, exist_ok=True)
                    response_path.write_text(raw_response, encoding="utf-8")
                except (KeyError, FileNotFoundError) as exc:
                    result_path = quarantine_dir / f"{item_key}.json"
                    error_messages = self._error_messages(exc)
                    write_json(
                        result_path,
                        {
                            "request": request.model_dump(mode="json"),
                            "raw_response": raw_response,
                            "errors": error_messages,
                        },
                    )
                    records.append(
                        GenerationRecord(
                            request_id=request.request_id,
                            iteration=iteration,
                            asset_kind=request.asset_kind,
                            status=GenerationStatus.QUARANTINED,
                            prompt_path=str(prompt_payload_path),
                            response_path=str(response_path),
                            result_path=str(result_path),
                            errors=error_messages,
                        )
                    )
                    continue

                try:
                    asset = self._parse_asset(raw_response, request.asset_kind)
                    self._validate_asset(asset, request)
                    result_path = promoted_dir / SUBDIR_BY_KIND[request.asset_kind] / f"{asset.id}.json"
                    write_json(result_path, asset)
                    records.append(
                        GenerationRecord(
                            request_id=request.request_id,
                            iteration=iteration,
                            asset_kind=request.asset_kind,
                            status=GenerationStatus.PROMOTED,
                            asset_id=asset.id,
                            prompt_path=str(prompt_payload_path),
                            response_path=str(response_path),
                            result_path=str(result_path),
                        )
                    )
                except (json.JSONDecodeError, ValidationError, SemanticValidationError, FileNotFoundError, KeyError) as exc:
                    result_path = quarantine_dir / f"{item_key}.json"
                    error_messages = self._error_messages(exc)
                    write_json(
                        result_path,
                        {
                            "request": request.model_dump(mode="json"),
                            "raw_response": raw_response,
                            "errors": error_messages,
                        },
                    )
                    records.append(
                        GenerationRecord(
                            request_id=request.request_id,
                            iteration=iteration,
                            asset_kind=request.asset_kind,
                            status=GenerationStatus.QUARANTINED,
                            prompt_path=str(prompt_payload_path),
                            response_path=str(response_path),
                            result_path=str(result_path),
                            errors=error_messages,
                        )
                    )

        result = GenerationBatchResult(
            batch_id=batch_id,
            records=records,
            promoted_count=sum(1 for record in records if record.status == GenerationStatus.PROMOTED),
            quarantined_count=sum(1 for record in records if record.status == GenerationStatus.QUARANTINED),
        )
        write_json(batch_dir / "manifest.json", result)
        write_jsonl(batch_dir / "records.jsonl", [record.model_dump(mode="json") for record in records])
        return result

    def _render_prompt(
        self,
        template: str,
        request: GenerationRequest,
        iteration: int,
    ) -> str:
        context = dict(request.context)
        context.setdefault("iteration", iteration)
        context.setdefault("request_id", request.request_id)
        return template.format(**context)

    def _parse_asset(self, raw_response: str, asset_kind: AssetKind):
        payload = json.loads(raw_response)
        model_cls = MODEL_BY_KIND[asset_kind]
        return model_cls.model_validate(payload)

    def _validate_asset(self, asset, request: GenerationRequest) -> None:
        if request.asset_kind == AssetKind.SCENARIO:
            validate_scenario_semantics(asset)
            return

        if request.asset_kind == AssetKind.FORCE_PACKAGE:
            scenario_path = request.validation_context["scenario_path"]
            scenario = load_model(scenario_path, Scenario)
            validate_force_package_semantics(scenario, asset)
            return

        if request.asset_kind == AssetKind.COA:
            scenario_path = request.validation_context["scenario_path"]
            force_package_path = request.validation_context["force_package_path"]
            scenario = load_model(scenario_path, Scenario)
            force_package = load_model(force_package_path, ForcePackage)
            validate_coa_semantics(scenario, force_package, asset)
            return

        raise KeyError(f"Unsupported asset kind {request.asset_kind}")

    def _error_messages(self, exc: Exception) -> list[str]:
        if isinstance(exc, SemanticValidationError):
            return exc.errors
        if isinstance(exc, ValidationError):
            return [error["msg"] for error in exc.errors()]
        return [str(exc)]
