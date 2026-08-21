from __future__ import annotations

import json

from record_transcript_resume.api_provider import ApiProviderConfig, _json_at_path, _request_data


def test_custom_json_provider_expands_prompt_and_model_without_breaking_json() -> None:
    config = ApiProviderConfig(
        protocol="custom_json",
        base_url="https://example.invalid/summarize",
        model="modelo-x",
        request_template='{"input": {"text": {prompt_json}}, "model": {model_json}}',
        response_path="result.text",
    )

    endpoint, data = _request_data(config, 'Texto com "aspas"')

    assert endpoint == "https://example.invalid/summarize"
    assert json.loads(data) == {"input": {"text": 'Texto com "aspas"'}, "model": "modelo-x"}


def test_response_path_reads_nested_api_content() -> None:
    assert _json_at_path({"result": {"choices": [{"text": "ok"}]}}, "result.choices.0.text") == "ok"
