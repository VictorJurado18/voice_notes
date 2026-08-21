"""Configurable token-based JSON providers for summary generation.

The standard mode covers OpenAI-compatible APIs.  The custom JSON mode makes
the widget useful with providers that expose a different REST envelope while
keeping the credential in Windows Credential Manager rather than in a file.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib import error, request

from record_transcript_resume.errors import SynthesisError
from record_transcript_resume.paths import app_data_dir


@dataclass(frozen=True)
class ApiProviderConfig:
    name: str = "Minha API"
    protocol: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    request_template: str = '{"model": {model_json}, "messages": [{"role": "user", "content": {prompt_json}}]}'
    response_path: str = "choices.0.message.content"


def _config_path() -> Path:
    return app_data_dir() / "api-provider.json"


def load_config() -> ApiProviderConfig:
    try:
        raw = json.loads(_config_path().read_text(encoding="utf-8"))
        allowed = {field.name for field in ApiProviderConfig.__dataclass_fields__.values()}
        # Older installations only have name/base_url/model; defaults preserve them.
        return ApiProviderConfig(**{key: value for key, value in raw.items() if key in allowed})
    except (OSError, ValueError, TypeError):
        return ApiProviderConfig()


def save_config(config: ApiProviderConfig, token: str) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        import keyring
        keyring.set_password("Voice Notes", "api-provider-token", token.strip())
    except Exception as exc:
        raise SynthesisError("Não foi possível salvar o token no Cofre de Credenciais do Windows.") from exc


def has_token() -> bool:
    try:
        import keyring
        return bool(keyring.get_password("Voice Notes", "api-provider-token"))
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


def generate(prompt: str) -> str:
    config = load_config()
    try:
        import keyring
        token = keyring.get_password("Voice Notes", "api-provider-token") or ""
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
