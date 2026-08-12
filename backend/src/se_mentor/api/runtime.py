from __future__ import annotations

import json
import logging
import os
import socket
from pathlib import Path
from tempfile import gettempdir
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from dataclasses import dataclass
from sqlalchemy.orm import Session, sessionmaker

from se_mentor.credentials.store import CredentialStatus, CredentialStore, InMemoryKeyring, KeyringUnavailable, SystemKeyring
from se_mentor.db.base import Base
from se_mentor.db.session import create_session_factory, create_sqlite_engine
import se_mentor.models  # noqa: F401
from se_mentor.llm.base import (
    LLMProvider,
    ProviderAuthError,
    ProviderConfigError,
    ProviderError,
    ProviderRequestError,
    ProviderRequestBuildError,
    ProviderTimeout,
)
from se_mentor.llm.openai_provider import OpenAIProviderConfig, OpenAIResponsesProvider
from se_mentor.security.secrets import Secret

_ENGINE = create_sqlite_engine(f"sqlite:///{Path(gettempdir()) / 'se_mentor_api.sqlite3'}")
Base.metadata.create_all(_ENGINE)
SESSION_FACTORY = create_session_factory(_ENGINE)

def _build_credential_store() -> CredentialStore:
    try:
        return CredentialStore(profile_id="default", keyring=SystemKeyring())
    except KeyringUnavailable:
        return CredentialStore(profile_id="default", keyring=InMemoryKeyring(fail_operations=True))


_CREDENTIAL_STORE = _build_credential_store()
LOGGER = logging.getLogger("se_mentor.provider")
_DEFAULT_OPENAI_TIMEOUT_SECONDS = 120
_MAX_OPENAI_TIMEOUT_SECONDS = 180


@dataclass
class ProviderRuntimeConfig:
    base_url: str | None = None
    model: str | None = None


_PROVIDER_CONFIG = ProviderRuntimeConfig()


def get_session_factory() -> sessionmaker[Session]:
    return SESSION_FACTORY


def get_credential_store() -> CredentialStore:
    return _CREDENTIAL_STORE


def set_provider_config(*, base_url: str | None, model: str | None) -> None:
    _PROVIDER_CONFIG.base_url = _normalize_base_url(base_url)
    _PROVIDER_CONFIG.model = model.strip() if model else None
    get_credential_store().set_provider_metadata(
        base_url=_PROVIDER_CONFIG.base_url,
        model=_PROVIDER_CONFIG.model,
    )


def clear_provider_config() -> None:
    _PROVIDER_CONFIG.base_url = None
    _PROVIDER_CONFIG.model = None
    get_credential_store().clear_provider_metadata()


def get_provider_config() -> ProviderRuntimeConfig:
    return ProviderRuntimeConfig(base_url=_PROVIDER_CONFIG.base_url, model=_PROVIDER_CONFIG.model)


def credential_status_payload(status: CredentialStatus) -> dict[str, object]:
    env_configured = bool(os.environ.get("SE_MENTOR_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    config = _resolved_provider_config()
    return {
        "configured": status.has_key or env_configured,
        "provider": "OpenAI",
        "source": _source_label(status) if status.has_key else _environment_source_label(env_configured),
        "baseUrl": config.base_url,
        "model": config.model,
    }


def get_domain_provider() -> LLMProvider:
    profile = os.environ.get("SE_MENTOR_LLM_PROFILE", "LOCAL_FULL").upper()
    if profile == "MOCK":
        raise ProviderAuthError("MOCK provider is only available through explicit test injection")
    try:
        secret = get_credential_store().provider().get_secret("openai")
        credential_source = "settings"
    except KeyError as exc:
        api_key = os.environ.get("SE_MENTOR_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ProviderAuthError("PROVIDER_UNAVAILABLE") from exc
        secret = Secret(api_key)
        credential_source = "env"
    config = _resolved_provider_config()
    if not config.base_url:
        raise ProviderConfigError("OpenAI-compatible base_url is not configured")
    _validate_base_url(config.base_url)
    if not config.model:
        raise ProviderConfigError("OpenAI-compatible model is not configured")
    LOGGER.info(
        "[provider] resolved provider=openai-compatible credential_source=%s base_url_host=%s model=%s",
        credential_source,
        _host(config.base_url),
        config.model,
    )
    return build_openai_provider(secret, config=config, credential_source=credential_source)


def build_openai_provider(
    secret: Secret,
    *,
    config: ProviderRuntimeConfig | None = None,
    credential_source: str = "settings",
) -> OpenAIResponsesProvider:
    resolved = config or _resolved_provider_config()
    if not resolved.base_url:
        raise ProviderConfigError("OpenAI-compatible base_url is not configured")
    _validate_base_url(resolved.base_url)
    if not resolved.model:
        raise ProviderConfigError("OpenAI-compatible model is not configured")
    return OpenAIResponsesProvider(
        client=_OpenAIHTTPClient(secret, base_url=resolved.base_url, credential_source=credential_source),
        config=OpenAIProviderConfig(
            model=resolved.model,
            request_timeout_seconds=_openai_timeout_seconds(),
        ),
    )


def _source_label(status: CredentialStatus) -> str:
    if not status.has_key:
        return "未配置"
    if status.persistence == "keyring":
        return "Windows 凭据管理器"
    return "仅本次运行有效"


def _environment_source_label(configured: bool) -> str:
    return "环境变量" if configured else "未配置"


class _OpenAIHTTPClient:
    def __init__(self, secret: Secret, *, base_url: str, credential_source: str) -> None:
        self.responses = _OpenAIHTTPResponses(secret, base_url=base_url, credential_source=credential_source)


class _OpenAIHTTPResponses:
    def __init__(self, secret: Secret, *, base_url: str, credential_source: str) -> None:
        self._secret = secret
        self._base_url = base_url
        self._credential_source = credential_source

    def create(self, **kwargs: object) -> object:
        LOGGER.info("[provider] request BUILD START contract=chat_completions base_url_host=%s", _host(self._base_url))
        try:
            api_key = self._secret.reveal()
            body = _chat_completion_body(kwargs)
            endpoint = f"{self._base_url.rstrip('/')}/chat/completions"
            timeout = int(kwargs.get("timeout", _DEFAULT_OPENAI_TIMEOUT_SECONDS))
            request = urlrequest.Request(
                endpoint,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
        except ProviderError:
            raise
        except Exception as exc:
            safe_message = _sanitize(str(exc))
            LOGGER.exception(
                "[provider] request BUILD FAILED error_type=%s error=%s",
                type(exc).__name__,
                safe_message,
            )
            raise ProviderRequestBuildError(
                f"provider request build failed: {type(exc).__name__}: {safe_message}"
            ) from exc
        LOGGER.info(
            "[provider] request SEND START provider=openai-compatible credential_source=%s base_url_host=%s model=%s",
            self._credential_source,
            _host(self._base_url),
            kwargs.get("model"),
        )
        try:
            with urlrequest.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                LOGGER.info("[provider] response RECEIVED status=%s type=chat_completions", response.status)
        except urlerror.HTTPError as exc:
            LOGGER.warning(
                "[provider] request FAILED error_type=HTTPError status=%s error=%s",
                exc.code,
                _sanitize(str(exc)),
            )
            raise _HTTPProviderError(exc.code) from exc
        except (TimeoutError, socket.timeout) as exc:
            LOGGER.warning(
                "[provider] request FAILED error_type=TimeoutError timeout_seconds=%s error=%s",
                timeout,
                _sanitize(str(exc)),
            )
            raise ProviderTimeout(f"OpenAI request timed out after {timeout}s") from exc
        except urlerror.URLError as exc:
            LOGGER.warning(
                "[provider] request FAILED error_type=URLError error=%s",
                _sanitize(str(exc)),
            )
            if _is_url_timeout(exc):
                raise ProviderTimeout(f"OpenAI request timed out after {timeout}s") from exc
            raise ProviderRequestError("OpenAI request failed") from exc
        except json.JSONDecodeError as exc:
            LOGGER.warning(
                "[provider] request FAILED error_type=JSONDecodeError error=%s",
                _sanitize(str(exc)),
            )
            raise ProviderRequestError("OpenAI returned a non-JSON response") from exc
        return _OpenAIResponse(payload)


class _HTTPProviderError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"OpenAI HTTP error {status_code}")
        self.status_code = status_code


class _OpenAIResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.output_text = _output_text(payload)
        usage = payload.get("usage")
        self.usage = _usage(usage) if isinstance(usage, dict) else {}


def _output_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list):
        chunks: list[str] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                chunks.append(message["content"])
        if chunks:
            return "".join(chunks)
    text = payload.get("output_text")
    if isinstance(text, str):
        return text
    chunks: list[str] = []
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    chunks.append(block["text"])
    return "".join(chunks)


def _chat_completion_body(kwargs: dict[str, object]) -> dict[str, object]:
    model = kwargs.get("model")
    input_text = kwargs.get("input")
    response_schema = kwargs.get("response_schema")
    if not isinstance(model, str) or not model.strip():
        raise ProviderConfigError("model is required")
    if not isinstance(input_text, str) or not input_text.strip():
        raise ProviderRequestBuildError("input text is required")
    body: dict[str, object] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are SE-Mentor's proposal generator. Return only valid JSON matching the "
                    "schema described in the user message. Do not wrap it in markdown. "
                    "All user-facing natural-language values in the JSON MUST be Simplified Chinese "
                    "(zh-CN). Keep JSON property names and enum values unchanged."
                ),
            },
            {"role": "user", "content": input_text},
        ],
        "temperature": 0,
    }
    if isinstance(response_schema, dict):
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "se_mentor_proposal",
                "schema": response_schema,
                "strict": True,
            },
        }
    return body


def _resolved_provider_config() -> ProviderRuntimeConfig:
    metadata = get_credential_store().provider_metadata()
    return ProviderRuntimeConfig(
        base_url=_PROVIDER_CONFIG.base_url
        or _normalize_base_url(metadata.get("base_url"))
        or _normalize_base_url(os.environ.get("SE_MENTOR_OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL")),
        model=_PROVIDER_CONFIG.model
        or metadata.get("model")
        or os.environ.get("SE_MENTOR_OPENAI_MODEL")
        or os.environ.get("OPENAI_MODEL"),
    )


def _openai_timeout_seconds() -> int:
    raw = os.environ.get("SE_MENTOR_OPENAI_TIMEOUT")
    if raw is None:
        return _DEFAULT_OPENAI_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ProviderConfigError("SE_MENTOR_OPENAI_TIMEOUT must be an integer number of seconds") from exc
    if value <= 0:
        raise ProviderConfigError("SE_MENTOR_OPENAI_TIMEOUT must be positive")
    return min(value, _MAX_OPENAI_TIMEOUT_SECONDS)


def _is_url_timeout(exc: urlerror.URLError) -> bool:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return True
    return "timed out" in str(reason).lower()


def _usage(usage: dict[str, Any]) -> dict[str, int]:
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    return {
        "input_tokens": input_tokens if isinstance(input_tokens, int) and input_tokens >= 0 else 0,
        "output_tokens": output_tokens if isinstance(output_tokens, int) and output_tokens >= 0 else 0,
    }


def _normalize_base_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")].rstrip("/")
    return normalized or None


def _validate_base_url(value: str) -> None:
    parsed = urlparse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProviderConfigError("OpenAI-compatible base_url must include http(s) scheme and host")


def _host(value: str | None) -> str:
    if not value:
        return "not-configured"
    return urlparse.urlparse(value).netloc or "invalid-url"


def _sanitize(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ")
