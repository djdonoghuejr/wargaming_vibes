from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
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


def _build_default_openai_client(api_key: str | None = None) -> Any:
    from openai import OpenAI

    return OpenAI(api_key=api_key)


class OpenAIResponsesGenerationProvider:
    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        client: Any | None = None,
        client_factory: Callable[[str | None], Any] | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        instructions: str | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self.instructions = instructions
        self._client = client
        self._api_key = api_key
        self._client_factory = client_factory or _build_default_openai_client

    def generate(self, prompt: str, request: GenerationRequest, iteration: int) -> str:
        client = self._client or self._client_factory(self._api_key)
        self._client = client

        if not hasattr(client, "responses") or not hasattr(client.responses, "create"):
            raise RuntimeError(
                "The configured OpenAI client does not support responses.create. "
                "Install a current openai SDK version and try again."
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            "store": False,
            "metadata": {
                "request_id": request.request_id,
                "iteration": str(iteration),
                "asset_kind": request.asset_kind.value,
            },
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.max_output_tokens is not None:
            payload["max_output_tokens"] = self.max_output_tokens
        if self.instructions:
            payload["instructions"] = self.instructions
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}

        try:
            response = client.responses.create(**payload)
        except Exception as exc:
            raise RuntimeError(
                f"OpenAI generation failed for {request.request_id}:{iteration}: {exc}"
            ) from exc
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        raise RuntimeError(
            f"OpenAI response for {request.request_id}:{iteration} did not include output_text."
        )
