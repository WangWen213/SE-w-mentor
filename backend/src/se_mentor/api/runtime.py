from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from tempfile import gettempdir
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

import se_mentor.models  # noqa: F401
from se_mentor.credentials.store import (
    CredentialStatus,
    CredentialStore,
    InMemoryKeyring,
    KeyringUnavailable,
    SystemKeyring,
    WindowsCredentialManagerKeyring,
)
from se_mentor.db.base import Base
from se_mentor.db.session import create_session_factory, create_sqlite_engine
from se_mentor.llm.base import (
    LLMProvider,
    ProviderAuthError,
    ProviderConfigError,
    ProviderError,
    ProviderRequestBuildError,
    ProviderRequestError,
    ProviderTimeout,
)
from se_mentor.llm.mock import MockLLMProvider, MockResponse
from se_mentor.llm.openai_provider import OpenAIProviderConfig, OpenAIResponsesProvider
from se_mentor.runtime.demo import ensure_demo_workspace
from se_mentor.runtime.profiles import RuntimeProfile  # noqa: I001
from se_mentor.runtime.profiles import get_runtime_settings as resolve_runtime_settings
from se_mentor.security.secrets import Secret

_RUNTIME_SETTINGS = resolve_runtime_settings()
_RUNTIME_SETTINGS.runtime_root.mkdir(parents=True, exist_ok=True)
if _RUNTIME_SETTINGS.profile is RuntimeProfile.CLOUD_DEMO:
    ensure_demo_workspace(_RUNTIME_SETTINGS.demo_workspace_root)

_DATABASE_URL = os.environ.get("SE_MENTOR_DATABASE_URL") or (
    f"sqlite:///{Path(gettempdir()) / 'se_mentor_api.sqlite3'}"
    if _RUNTIME_SETTINGS.profile is RuntimeProfile.LOCAL_FULL
    else f"sqlite:///{_RUNTIME_SETTINGS.runtime_root / 'se_mentor_api.sqlite3'}"
)
_ENGINE = create_sqlite_engine(_DATABASE_URL)
Base.metadata.create_all(_ENGINE)
Base.metadata.create_all(_ENGINE, tables=[Base.metadata.tables["task_evaluations"]])


def _build_credential_store() -> CredentialStore:
    if _RUNTIME_SETTINGS.profile is RuntimeProfile.CLOUD_DEMO:
        return CredentialStore(
            profile_id="cloud-demo", keyring=InMemoryKeyring(fail_operations=True)
        )
    if _RUNTIME_SETTINGS.profile is RuntimeProfile.ONLINE_SAFE:
        return CredentialStore(
            profile_id="online-safe-locked",
            keyring=InMemoryKeyring(fail_operations=True),
        )
    for keyring_factory in (WindowsCredentialManagerKeyring, SystemKeyring):
        try:
            store = CredentialStore(profile_id="default", keyring=keyring_factory())
            store.require_persistent_credentials()
            return store
        except KeyringUnavailable:
            continue
    return CredentialStore(profile_id="default", keyring=InMemoryKeyring(fail_operations=True))


_CREDENTIAL_STORE = _build_credential_store()
LOGGER = logging.getLogger("se_mentor.provider")
_DEFAULT_OPENAI_TIMEOUT_SECONDS = 120
_MAX_OPENAI_TIMEOUT_SECONDS = 180


def _ensure_runtime_schema_compatibility() -> None:
    with _ENGINE.begin() as connection:
        ddl = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='knowledge_sources'")
        ).scalar_one_or_none()
    if ddl is None or "GOVERNANCE_AUDIT" in str(ddl):
        return
    legacy = "knowledge_sources_legacy_runtime_compat"
    with _ENGINE.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {legacy}"))
        connection.execute(text(f"ALTER TABLE knowledge_sources RENAME TO {legacy}"))
    Base.metadata.create_all(_ENGINE, tables=[Base.metadata.tables["knowledge_sources"]])
    with _ENGINE.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO knowledge_sources "
                "(id, knowledge_id, source_type, source_ref, evidence_json, created_at) "
                f"SELECT id, knowledge_id, source_type, source_ref, evidence_json, created_at "
                f"FROM {legacy}"
            )
        )
        connection.execute(text(f"DROP TABLE {legacy}"))


_ensure_runtime_schema_compatibility()
SESSION_FACTORY = create_session_factory(_ENGINE)


@dataclass
class ProviderRuntimeConfig:
    base_url: str | None = None
    model: str | None = None


_PROVIDER_CONFIG = ProviderRuntimeConfig()
ONLINE_SAFE_CREDENTIAL_ERROR = "ONLINE_SAFE_SESSION_CREDENTIALS_NOT_READY"
ONLINE_SAFE_PROVIDER_ERROR = "ONLINE_SAFE_PROVIDER_NOT_READY"
ONLINE_SAFE_WORKSPACE_ERROR = "ONLINE_SAFE_WORKSPACE_NOT_READY"


class OnlineSafeNotReadyError(ProviderConfigError):
    pass


class ProviderFactory:
    def __init__(self, credential_store: CredentialStore) -> None:
        self.credential_store = credential_store

    def create(self) -> LLMProvider:
        if _RUNTIME_SETTINGS.profile is RuntimeProfile.ONLINE_SAFE:
            raise OnlineSafeNotReadyError(ONLINE_SAFE_PROVIDER_ERROR)
        profile = os.environ.get("SE_MENTOR_LLM_PROFILE", "LOCAL_FULL").upper()
        if profile == "MOCK":
            raise ProviderAuthError(
                "MOCK provider is only available through explicit test injection"
            )
        try:
            secret = self.credential_store.provider().get_secret("openai")
            credential_source = "settings"
        except KeyError as exc:
            api_key = os.environ.get("SE_MENTOR_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ProviderAuthError("PROVIDER_UNAVAILABLE") from exc
            secret = Secret(api_key)
            credential_source = "env"
        config = _resolved_provider_config(self.credential_store)
        if not config.base_url:
            raise ProviderConfigError("OpenAI-compatible base_url is not configured")
        _validate_base_url(config.base_url)
        if not config.model:
            raise ProviderConfigError("OpenAI-compatible model is not configured")
        LOGGER.info(
            "[provider] resolved provider=openai-compatible credential_source=%s "
            "base_url_host=%s model=%s",
            credential_source,
            _host(config.base_url),
            config.model,
        )
        return build_openai_provider(secret, config=config, credential_source=credential_source)


def get_session_factory() -> sessionmaker[Session]:
    return SESSION_FACTORY


def get_credential_store() -> CredentialStore:
    return _CREDENTIAL_STORE


def get_runtime_settings():
    return _RUNTIME_SETTINGS


def set_provider_config(*, base_url: str | None, model: str | None) -> None:
    if _RUNTIME_SETTINGS.profile is RuntimeProfile.ONLINE_SAFE:
        raise OnlineSafeNotReadyError(ONLINE_SAFE_CREDENTIAL_ERROR)
    if _RUNTIME_SETTINGS.profile is RuntimeProfile.CLOUD_DEMO:
        raise ProviderConfigError("provider configuration is unavailable in CLOUD_DEMO")
    _PROVIDER_CONFIG.base_url = _normalize_base_url(base_url)
    _PROVIDER_CONFIG.model = model.strip() if model else None
    get_credential_store().set_provider_metadata(
        base_url=_PROVIDER_CONFIG.base_url,
        model=_PROVIDER_CONFIG.model,
    )


def clear_provider_config() -> None:
    if _RUNTIME_SETTINGS.profile is RuntimeProfile.ONLINE_SAFE:
        raise OnlineSafeNotReadyError(ONLINE_SAFE_CREDENTIAL_ERROR)
    if _RUNTIME_SETTINGS.profile is RuntimeProfile.CLOUD_DEMO:
        raise ProviderConfigError("provider configuration is unavailable in CLOUD_DEMO")
    _PROVIDER_CONFIG.base_url = None
    _PROVIDER_CONFIG.model = None
    get_credential_store().clear_provider_metadata()


def get_provider_config() -> ProviderRuntimeConfig:
    return _resolved_provider_config()


def credential_status_payload(status: CredentialStatus | None) -> dict[str, object]:
    if _RUNTIME_SETTINGS.profile is RuntimeProfile.CLOUD_DEMO:
        return {
            "configured": True,
            "provider": "Mock",
            "source": "CLOUD_DEMO",
            "baseUrl": None,
            "model": "cloud-demo",
        }
    if _RUNTIME_SETTINGS.profile is RuntimeProfile.ONLINE_SAFE:
        return {
            "configured": False,
            "provider": "OpenAI",
            "source": "ONLINE_SAFE",
            "baseUrl": None,
            "model": None,
            "locked": True,
            "reason": ONLINE_SAFE_CREDENTIAL_ERROR,
        }
    env_configured = bool(
        os.environ.get("SE_MENTOR_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    )
    config = _resolved_provider_config()
    return {
        "configured": status.has_key or env_configured,
        "provider": "OpenAI",
        "source": _source_label(status)
        if status.has_key
        else _environment_source_label(env_configured),
        "baseUrl": config.base_url,
        "model": config.model,
    }


def get_domain_provider() -> LLMProvider:
    if _RUNTIME_SETTINGS.profile is RuntimeProfile.CLOUD_DEMO:
        return _cloud_demo_provider()
    if _RUNTIME_SETTINGS.profile is RuntimeProfile.ONLINE_SAFE:
        raise OnlineSafeNotReadyError(ONLINE_SAFE_PROVIDER_ERROR)
    return ProviderFactory(get_credential_store()).create()


def _cloud_demo_provider() -> MockLLMProvider:
    return MockLLMProvider(
        model="cloud-demo",
        script=(
            MockResponse(
                match="requires_code_change=true",
                content=(
                    '{"action_type":"APPLY_PATCH","parameters":{"relative_path":"app.py",'
                    '"expected_sha256":null,"replacements":[{"old":"return f\\"Hello, {name}!\\"",'
                    '"new":"return f\\"Hello from SE-Mentor, {name}!\\""}],'
                    '"target_evidence":{"selected_path":"app.py",'
                    '"selected_excerpt":"return f\\"Hello, {name}!\\"",'
                    '"user_target_description":"update demo greeting text",'
                    '"matched_semantic_evidence":["SEARCH_CODE:greeting"],'
                    '"alternative_candidates":[],'
                    '"selection_reason":"app.py contains the demo greeting function"}},'
                    '"reason":"Apply the confirmed demo greeting change."}'
                ),
                input_tokens=96,
                output_tokens=96,
                min_call=2,
            ),
            MockResponse(
                match="requires_code_change=true",
                content=(
                    '{"action_type":"SEARCH_CODE","parameters":{"query":"greeting"},'
                    '"reason":"Locate the demo greeting function."}'
                ),
                input_tokens=64,
                output_tokens=32,
            ),
            MockResponse(
                match="structured change proposal",
                content=(
                    '{"goal":"Improve demo greeting",'
                    '"understanding":"The demo project has a simple greeting function.",'
                    '"expected_behavior":"The greeting stays testable and becomes friendlier.",'
                    '"scope":["app.py"],'
                    '"changes":[{"path":"app.py","symbol":"greeting","action":"update",'
                    '"reason":"app.py owns the greeting behavior"}],'
                    '"steps":["Read app.py","Update the greeting text","Run the demo test"],'
                    '"non_goals":[],"constraints":["Only modify the demo workspace"],'
                    '"acceptance":["test_app.py passes"],"validation":["pytest -q"],'
                    '"user_facts":[],"inferences":["This is a CLOUD_DEMO task"],'
                    '"risks":["The expected test assertion may need a later update"]}'
                ),
                input_tokens=128,
                output_tokens=128,
            ),
            MockResponse(
                match="structured change proposal",
                content=(
                    '{"goal":"改进演示问候语","understanding":"演示项目包含一个简单问候函数。",'
                    '"expected_behavior":"问候语保持可测试且更友好。","scope":["app.py"],'
                    '"changes":[{"path":"app.py","symbol":"greeting","action":"update",'
                    '"reason":"演示受控代码修改"}],"steps":["读取 app.py",'
                    '"更新问候文本","运行演示测试"],'
                    '"non_goals":[],"constraints":["仅限演示工作区"],'
                    '"acceptance":["test_app.py 通过"],"validation":["pytest -q"],'
                    '"user_facts":[],"inferences":["这是 CLOUD_DEMO 演示任务"],"risks":[]}'
                ),
                input_tokens=128,
                output_tokens=128,
            ),
            MockResponse(
                match="bundle_hash",
                content='{"narrative":"演示变更影响范围仅限 app.py。","risks":[],"fact_refs":[]}',
                input_tokens=64,
                output_tokens=32,
            ),
            MockResponse(
                match="execution",
                content=(
                    '{"action_type":"SEARCH_CODE","parameters":{"query":"greeting"},'
                    '"reason":"定位演示问候函数"}'
                ),
                input_tokens=64,
                output_tokens=32,
            ),
        ),
    )


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
        client=_OpenAIHTTPClient(
            secret, base_url=resolved.base_url, credential_source=credential_source
        ),
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
        self.responses = _OpenAIHTTPResponses(
            secret, base_url=base_url, credential_source=credential_source
        )


class _OpenAIHTTPResponses:
    def __init__(self, secret: Secret, *, base_url: str, credential_source: str) -> None:
        self._secret = secret
        self._base_url = base_url
        self._credential_source = credential_source

    def create(self, **kwargs: object) -> object:
        LOGGER.info(
            "[provider] request BUILD START contract=chat_completions base_url_host=%s",
            _host(self._base_url),
        )
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
            "[provider] request SEND START provider=openai-compatible credential_source=%s "
            "base_url_host=%s model=%s",
            self._credential_source,
            _host(self._base_url),
            kwargs.get("model"),
        )
        try:
            with urlrequest.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                LOGGER.info(
                    "[provider] response RECEIVED status=%s type=chat_completions", response.status
                )
        except urlerror.HTTPError as exc:
            LOGGER.warning(
                "[provider] request FAILED error_type=HTTPError status=%s error=%s",
                exc.code,
                _sanitize(str(exc)),
            )
            raise _HTTPProviderError(exc.code) from exc
        except TimeoutError as exc:
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
                    "All user-facing natural-language values in the JSON MUST be "
                    "Simplified Chinese (zh-CN). Keep JSON property names and enum "
                    "values unchanged."
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
                "name": "se_mentor_structured_response",
                "schema": response_schema,
                "strict": True,
            },
        }
    else:
        text = kwargs.get("text")
        if isinstance(text, dict):
            text_format = text.get("format")
            if isinstance(text_format, dict) and text_format.get("type") == "json_schema":
                schema = text_format.get("schema")
                if isinstance(schema, dict):
                    body["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": str(text_format.get("name") or "se_mentor_structured_response"),
                            "schema": schema,
                            "strict": bool(text_format.get("strict", True)),
                        },
                    }
    return body


def _resolved_provider_config(store: CredentialStore | None = None) -> ProviderRuntimeConfig:
    metadata = (store or get_credential_store()).provider_metadata()
    return ProviderRuntimeConfig(
        base_url=_PROVIDER_CONFIG.base_url
        or _normalize_base_url(metadata.get("base_url"))
        or _normalize_base_url(
            os.environ.get("SE_MENTOR_OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
        ),
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
        raise ProviderConfigError(
            "SE_MENTOR_OPENAI_TIMEOUT must be an integer number of seconds"
        ) from exc
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
        "output_tokens": output_tokens
        if isinstance(output_tokens, int) and output_tokens >= 0
        else 0,
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
