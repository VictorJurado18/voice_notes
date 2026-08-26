from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from pathlib import Path

from record_transcript_resume import api_provider
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


def test_legacy_single_provider_is_migrated_to_provider_list(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api_provider, "app_data_dir", lambda: tmp_path)
    (tmp_path / "api-provider.json").write_text(
        json.dumps({"name": "API existente", "base_url": "https://example.test/v1", "model": "modelo"}),
        encoding="utf-8",
    )

    providers = api_provider.load_configs()

    assert len(providers) == 1
    assert providers[0].id == "legacy"
    assert providers[0].name == "API existente"
    saved = json.loads((tmp_path / "api-providers.json").read_text(encoding="utf-8"))
    assert saved["providers"][0]["id"] == "legacy"


def test_saving_provider_preserves_other_saved_providers(monkeypatch, tmp_path: Path) -> None:
    tokens: dict[str, str] = {}
    monkeypatch.setattr(api_provider, "app_data_dir", lambda: tmp_path)
    monkeypatch.setitem(
        sys.modules,
        "keyring",
        SimpleNamespace(set_password=lambda _service, key, token: tokens.__setitem__(key, token)),
    )

    first = api_provider.save_config(ApiProviderConfig(name="Primeira API"), "token-1")
    second = api_provider.save_config(ApiProviderConfig(name="Segunda API"), "token-2")
    api_provider.save_config(ApiProviderConfig(**{**second.__dict__, "model": "modelo-novo"}))

    providers = api_provider.load_configs()

    assert [provider.name for provider in providers] == ["Primeira API", "Segunda API"]
    assert providers[1].model == "modelo-novo"
    assert tokens[f"api-provider-token:{first.id}"] == "token-1"
    assert tokens[f"api-provider-token:{second.id}"] == "token-2"


def test_openai_compatible_provider_transcribes_audio_with_segments(monkeypatch, tmp_path: Path) -> None:
    audio = tmp_path / "reuniao.mp4"
    audio.write_bytes(b"video-bytes")
    config = ApiProviderConfig(
        id="transcribe-api", name="Minha API", base_url="https://example.test/v1",
        transcription_model="whisper-1",
    )
    request_seen: dict[str, object] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return '{"segments": [{"start": 1.2, "end": 3.4, "text": " Olá mundo "}]}'.encode("utf-8")

    def open_request(call, timeout: int):
        request_seen["url"] = call.full_url
        request_seen["data"] = call.data
        request_seen["authorization"] = call.get_header("Authorization")
        request_seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(api_provider, "load_configs", lambda: [config])
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=lambda *_args: "token-seguro"))
    monkeypatch.setattr(api_provider.request, "urlopen", open_request)

    segments = api_provider.transcribe_audio(audio, "pt", "transcribe-api")

    assert [(segment.start, segment.end, segment.text) for segment in segments] == [(1.2, 3.4, "Olá mundo")]
    assert request_seen["url"] == "https://example.test/v1/audio/transcriptions"
    assert request_seen["authorization"] == "Bearer token-seguro"
    assert b'name="response_format"' in request_seen["data"]
    assert b'filename="reuniao.mp4"' in request_seen["data"]
