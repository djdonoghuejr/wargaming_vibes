from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetKind(str, Enum):
    SCENARIO = "scenario"
    FORCE_PACKAGE = "force_package"
    COA = "coa"


class GenerationStatus(str, Enum):
    PROMOTED = "promoted"
    QUARANTINED = "quarantined"


class GenerationRequest(StrictModel):
    request_id: str
    asset_kind: AssetKind
    template_path: str
    count: int = Field(default=1, ge=1, le=100)
    context: dict[str, Any] = Field(default_factory=dict)
    validation_context: dict[str, str] = Field(default_factory=dict)


class GenerationRecord(StrictModel):
    request_id: str
    iteration: int = Field(ge=1)
    asset_kind: AssetKind
    status: GenerationStatus
    asset_id: str | None = None
    prompt_path: str
    response_path: str
    result_path: str
    errors: list[str] = Field(default_factory=list)


class GenerationBatchResult(StrictModel):
    batch_id: str
    records: list[GenerationRecord]
    promoted_count: int = Field(ge=0)
    quarantined_count: int = Field(ge=0)
