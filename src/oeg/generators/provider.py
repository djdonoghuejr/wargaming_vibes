from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from oeg.generators.models import GenerationRequest


class GenerationProvider(Protocol):
    def generate(self, prompt: str, request: GenerationRequest, iteration: int) -> str:
        raise NotImplementedError


class StaticGenerationProvider:
    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = responses

    def generate(self, prompt: str, request: GenerationRequest, iteration: int) -> str:
        del prompt
        request_key = f"{request.request_id}:{iteration}"
        if request_key in self._responses:
            return self._responses[request_key]
        if request.request_id in self._responses:
            return self._responses[request.request_id]
        raise KeyError(f"No static response configured for {request_key}")


class FileReplayGenerationProvider:
    def __init__(self, replay_path: str | Path) -> None:
        raw = json.loads(Path(replay_path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Replay file must be a JSON object mapping request keys to raw responses.")
        self._provider = StaticGenerationProvider(
            {str(key): str(value) for key, value in raw.items()}
        )

    def generate(self, prompt: str, request: GenerationRequest, iteration: int) -> str:
        return self._provider.generate(prompt, request, iteration)
