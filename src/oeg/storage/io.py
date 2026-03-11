from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import TypeVar

from pydantic import BaseModel

from oeg.schemas.models import AAR
from oeg.schemas.models import COAComparison
from oeg.schemas.models import EventLog
from oeg.schemas.models import LessonLearned
from oeg.schemas.models import RunManifest
from oeg.schemas.models import TurnState


ModelT = TypeVar("ModelT", bound=BaseModel)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def timestamp_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}"


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_model(path: str | Path, model_cls: type[ModelT]) -> ModelT:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return model_cls.model_validate(raw)


def _serialize(payload: Any) -> Any:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    return payload


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    ensure_directory(target.parent)
    target.write_text(
        json.dumps(_serialize(payload), indent=2),
        encoding="utf-8",
    )
    return target


def write_jsonl(path: str | Path, payloads: list[Any]) -> Path:
    target = Path(path)
    ensure_directory(target.parent)
    lines = [json.dumps(_serialize(item)) for item in payloads]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return target


def persist_run_bundle(
    output_root: str | Path,
    manifest: RunManifest,
    turn_states: list[TurnState],
    event_logs: list[EventLog],
    aar: AAR,
    lessons: list[LessonLearned],
) -> Path:
    root = ensure_directory(Path(output_root))
    run_dir = ensure_directory(root / manifest.id)
    manifest.output_dir = str(run_dir)

    write_json(run_dir / "manifest.json", manifest)
    write_jsonl(run_dir / "turn_states.jsonl", turn_states)
    write_jsonl(run_dir / "event_log.jsonl", event_logs)
    write_json(run_dir / "aar.json", aar)
    write_json(run_dir / "lessons.json", [item.model_dump(mode="json") for item in lessons])

    if turn_states:
        write_json(run_dir / "final_state.json", turn_states[-1])

    return run_dir


def persist_comparison_bundle(
    output_root: str | Path,
    comparison: COAComparison,
    run_dirs: list[Path],
) -> Path:
    root = ensure_directory(Path(output_root))
    comparison_dir = ensure_directory(root / comparison.id)
    write_json(comparison_dir / "comparison.json", comparison)
    write_json(
        comparison_dir / "manifest.json",
        {
            "comparison_id": comparison.id,
            "scenario_id": comparison.scenario_id,
            "run_directories": [str(item) for item in run_dirs],
        },
    )
    return comparison_dir
