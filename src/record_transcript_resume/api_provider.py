"""Configurable token-based JSON providers for summary generation.

The standard mode covers OpenAI-compatible APIs.  The custom JSON mode makes
the widget useful with providers that expose a different REST envelope while
keeping the credential in Windows Credential Manager rather than in a file.
"""
from __future__ import annotations

import json
import mimetypes
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib import error, request
from uuid import uuid4

from record_transcript_resume.errors import SynthesisError
from record_transcript_resume.paths import app_data_dir


@dataclass(frozen=True)
class ApiProviderConfig:
    id: str = ""
    name: str = "Minha API"
    protocol: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    transcription_model: str = "whisper-1"
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    request_template: str = '{"model": {model_json}, "messages": [{"role": "user", "content": {prompt_json}}]}'
    response_path: str = "choices.0.message.content"


def _config_path() -> Path:
    return app_data_dir() / "api-providers.json"


def _legacy_config_path() -> Path:
    return app_data_dir() / "api-provider.json"


def _token_key(provider_id: str) -> str:
    return f"api-provider-token:{provider_id}"


def _legacy_token_key() -> str:
    return "api-provider-token"


def _config_from_raw(raw: object, fallback_id: str = "") -> ApiProviderConfig | None:
    if not isinstance(raw, dict):
        return None
    allowed = {field.name for field in ApiProviderConfig.__dataclass_fields__.values()}
    values = {key: value for key, value in raw.items() if key in allowed}
    values["id"] = str(values.get("id") or fallback_id or uuid4().hex)
    try:
        return ApiProviderConfig(**values)
    except (TypeError, ValueError):
        return None


def _write_configs(configs: list[ApiProviderConfig]) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"providers": [asdict(config) for config in configs]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_configs() -> list[ApiProviderConfig]:
    """Load all saved API providers and migrate the former single provider."""
    try:
        raw = json.loads(_config_path().read_text(encoding="utf-8"))
        entries = raw.get("providers", []) if isinstance(raw, dict) else raw
        if isinstance(entries, list):
            return [config for entry in entries if (config := _config_from_raw(entry)) is not None]
    except (OSError, ValueError, TypeError):
        pass

    try:
        legacy = _config_from_raw(
            json.loads(_legacy_config_path().read_text(encoding="utf-8")),
            fallback_id="legacy",
        )
    except (OSError, ValueError, TypeError):
        legacy = None
    if legacy is None:
        return []
    _write_configs([legacy])
    return [legacy]


def load_config() -> ApiProviderConfig:
    """Compatibility helper for code that needs the first saved provider."""
    return next(iter(load_configs()), ApiProviderConfig())


def save_config(config: ApiProviderConfig, token: str | None = None) -> ApiProviderConfig:
    """Create or update one provider without replacing the others or its token."""
    provider_id = config.id.strip() or uuid4().hex
    saved = ApiProviderConfig(**{**asdict(config), "id": provider_id})
    configs = load_configs()
    replaced = False
    updated: list[ApiProviderConfig] = []
    for existing in configs:
        if existing.id == provider_id:
            updated.append(saved)
            replaced = True
        else:
            updated.append(existing)
    if not replaced:
        updated.append(saved)
    _write_configs(updated)
    if token is None or not token.strip():
        return saved
    try:
        import keyring
        keyring.set_password("Voice Notes", _token_key(provider_id), token.strip())
    except Exception as exc:
        raise SynthesisError("Não foi possível salvar o token no Cofre de Credenciais do Windows.") from exc
    return saved


def has_token(provider_id: str | None = None) -> bool:
    try:
        import keyring
        config = next((item for item in load_configs() if item.id == provider_id), None) if provider_id else load_config()
        if config is None:
            return False
        token = keyring.get_password("Voice Notes", _token_key(config.id))
        if token:
            return True
        # The former single-provider token is migrated lazily so existing
        # installations keep working without exposing or rewriting it in JSON.
        if config.id == "legacy":
            legacy = keyring.get_password("Voice Notes", _legacy_token_key())
            if legacy:
                keyring.set_password("Voice Notes", _token_key(config.id), legacy)
                return True
        return False
    except Exception:
        return False


def _json_at_path(payload: object, path: str) -> object:
    value = payload
    for part in (item.strip() for item in path.split(".") if item.strip()):
        if isinstance(value, list):
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise KeyError(part)
    return value


def _request_data(config: ApiProviderConfig, prompt: str) -> tuple[str, bytes]:
    if config.protocol == "openai_compatible":
        endpoint = config.base_url.rstrip("/") + "/chat/completions"
        payload: object = {
            "model": config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
    elif config.protocol == "custom_json":
        endpoint = config.base_url.strip()
        template = config.request_template.strip()
        if not endpoint or not template:
            raise SynthesisError("Informe a URL completa e o corpo JSON do provider personalizado.")
        rendered = (
            template.replace("{prompt_json}", json.dumps(prompt, ensure_ascii=False))
            .replace("{model_json}", json.dumps(config.model, ensure_ascii=False))
        )
        try:
            payload = json.loads(rendered)
        except ValueError as exc:
            raise SynthesisError("O corpo JSON personalizado não é válido.") from exc
    else:
        raise SynthesisError("Tipo de provider de API inválido.")
    return endpoint, json.dumps(payload, ensure_ascii=False).encode("utf-8")


def generate(prompt: str, provider_id: str | None = None) -> str:
    configs = load_configs()
    config = next((item for item in configs if item.id == provider_id), None) if provider_id else next(iter(configs), None)
    if config is None:
        raise SynthesisError("Cadastre um provider por API antes de usar este provider.")
    try:
        import keyring
        token = keyring.get_password("Voice Notes", _token_key(config.id)) or ""
        if not token and config.id == "legacy":
            token = keyring.get_password("Voice Notes", _legacy_token_key()) or ""
    except Exception as exc:
        raise SynthesisError("Não foi possível ler o token salvo da API.") from exc
    if not token:
        raise SynthesisError("Cadastre o token da API em Configurar antes de usar este provider.")

    endpoint, payload = _request_data(config, prompt)
    auth_value = f"{config.auth_prefix}{token}" if config.auth_header.strip() else ""
    headers = {"Content-Type": "application/json"}
    if auth_value:
        headers[config.auth_header.strip()] = auth_value
    call = request.Request(endpoint, data=payload, method="POST", headers=headers)
    try:
        with request.urlopen(call, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = _json_at_path(body, config.response_path)
        if isinstance(content, (dict, list)):
            return json.dumps(content, ensure_ascii=False)
        return str(content).strip()
    except (error.URLError, error.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise SynthesisError(
            f"A API de {config.name} não respondeu como esperado: {exc}"
        ) from exc


def transcribe_audio(audio_path: Path, language: str | None, provider_id: str) -> list[object]:
    """Transcribe one file with an OpenAI-compatible audio endpoint.

    The endpoint returns ``verbose_json`` so the rest of the app keeps its
    timestamped transcript flow. Other JSON envelopes remain summary-only on
    purpose: accepting an arbitrary audio schema would hide incompatible API
    calls behind a misleading provider selector.
    """
    if not audio_path.is_file():
        raise SynthesisError(f"Não foi possível encontrar o arquivo para enviar: {audio_path}")
    supported_extensions = {".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"}
    if audio_path.suffix.casefold() not in supported_extensions:
        raise SynthesisError(
            "A transcrição por API aceita FLAC, MP3, MP4, MPEG, MPGA, M4A, OGG, WAV ou WEBM. "
            "Para este arquivo, escolha Whisper local."
        )
    config = next((item for item in load_configs() if item.id == provider_id), None)
    if config is None:
        raise SynthesisError("O provider de transcrição selecionado não foi encontrado.")
    if config.protocol != "openai_compatible":
        raise SynthesisError("Este provider usa JSON personalizado e não é compatível com transcrição por áudio.")
    try:
        import keyring
        token = keyring.get_password("Voice Notes", _token_key(config.id)) or ""
        if not token and config.id == "legacy":
            token = keyring.get_password("Voice Notes", _legacy_token_key()) or ""
    except Exception as exc:
        raise SynthesisError("Não foi possível ler o token salvo da API.") from exc
    if not token:
        raise SynthesisError(f"O provider {config.name} não possui um token salvo.")

    boundary = f"----VoiceNotes{uuid4().hex}"
    fields = {
        "model": config.transcription_model.strip() or "whisper-1",
        "response_format": "verbose_json",
    }
    if language:
        fields["language"] = language
    body = _multipart_audio_body(boundary, fields, audio_path)
    endpoint = config.base_url.rstrip("/") + "/audio/transcriptions"
    auth_value = f"{config.auth_prefix}{token}" if config.auth_header.strip() else ""
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if auth_value:
        headers[config.auth_header.strip()] = auth_value
    call = request.Request(endpoint, data=body, method="POST", headers=headers)
    try:
        with request.urlopen(call, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, OSError, ValueError) as exc:
        raise SynthesisError(f"A transcrição por API de {config.name} falhou: {exc}") from exc
    return _segments_from_transcription_response(payload)


def _multipart_audio_body(boundary: str, fields: dict[str, str], audio_path: Path) -> bytes:
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.extend((
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ))
    mime_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
    parts.extend((
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"\r\n'.encode(),
        f"Content-Type: {mime_type}\r\n\r\n".encode(),
        audio_path.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ))
    return b"".join(parts)


def _segments_from_transcription_response(payload: object) -> list[object]:
    """Normalize an OpenAI verbose response without importing transcription at module load."""
    from record_transcript_resume.transcription import Segment

    if not isinstance(payload, dict):
        raise SynthesisError("A API de transcrição retornou uma resposta inválida.")
    segments: list[Segment] = []
    raw_segments = payload.get("segments")
    if isinstance(raw_segments, list):
        for entry in raw_segments:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text", "")).strip()
            if not text:
                continue
            try:
                start = float(entry.get("start", 0))
                end = float(entry.get("end", start))
            except (TypeError, ValueError):
                continue
            segments.append(Segment(start=start, end=end, text=text))
    if segments:
        return segments
    text = str(payload.get("text", "")).strip()
    if text:
        return [Segment(start=0.0, end=0.0, text=text)]
    raise SynthesisError("A API de transcrição não retornou texto utilizável.")
