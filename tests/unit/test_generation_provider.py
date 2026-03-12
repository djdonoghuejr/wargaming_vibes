from __future__ import annotations

from types import SimpleNamespace

import pytest

from oeg.generators import AssetKind
from oeg.generators import GenerationRequest
from oeg.generators.provider import OpenAIResponsesGenerationProvider


class _FakeResponsesApi:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **payload):
        self.calls.append(payload)
        return SimpleNamespace(output_text='{"id":"generated"}')


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponsesApi()


def test_openai_provider_calls_responses_api_with_expected_payload() -> None:
    client = _FakeClient()
    provider = OpenAIResponsesGenerationProvider(
        model="gpt-5-mini",
        client=client,
        temperature=0.2,
        max_output_tokens=1200,
        reasoning_effort="minimal",
    )
    request = GenerationRequest(
        request_id="scenario_batch",
        asset_kind=AssetKind.SCENARIO,
        template_path="unused.md",
        context={"scenario_family": "corridor_delay"},
    )

    response = provider.generate(
        prompt="Return JSON only.",
        request=request,
        iteration=2,
    )

    assert response == '{"id":"generated"}'
    assert len(client.responses.calls) == 1
    payload = client.responses.calls[0]
    assert payload["model"] == "gpt-5-mini"
    assert payload["input"] == "Return JSON only."
    assert payload["temperature"] == 0.2
    assert payload["max_output_tokens"] == 1200
    assert payload["reasoning"] == {"effort": "minimal"}
    assert payload["metadata"]["request_id"] == "scenario_batch"
    assert payload["metadata"]["iteration"] == "2"
    assert payload["metadata"]["asset_kind"] == "scenario"


def test_openai_provider_rejects_clients_without_responses_api() -> None:
    provider = OpenAIResponsesGenerationProvider(
        model="gpt-5-mini",
        client=object(),
    )
    request = GenerationRequest(
        request_id="scenario_batch",
        asset_kind=AssetKind.SCENARIO,
        template_path="unused.md",
    )

    with pytest.raises(RuntimeError, match="responses.create"):
        provider.generate("Return JSON only.", request, 1)
