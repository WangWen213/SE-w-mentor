from __future__ import annotations

import json
import logging

import pytest

from se_mentor.security.process_env import build_child_env
from se_mentor.security.redaction import RedactionError, redact_exception, redact_text
from se_mentor.security.secrets import AgentContext, CredentialProvider, Secret


def test_AC_SEC_05_child_process_cannot_read_llm_key() -> None:
    parent_env = {
        "PATH": "C:/Windows/System32",
        "SystemRoot": "C:/Windows",
        "TMP": "C:/Temp",
        "TEMP": "C:/Temp",
        "OPENAI_API_KEY": "sk-proj-secret",
        "ALIBABA_CLOUD_ACCESS_KEY_ID": "LTAI5secret",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "aliyun-secret",
        "USERPROFILE": "C:/Users/ww",
        "RANDOM_SERVICE_TOKEN": "ghp_secretsecretsecret",
    }

    child_env = build_child_env(parent_env)

    assert child_env == {
        "PATH": "C:/Windows/System32",
        "SystemRoot": "C:/Windows",
        "TMP": "C:/Temp",
        "TEMP": "C:/Temp",
    }
    assert "OPENAI_API_KEY" not in child_env
    assert "ALIBABA_CLOUD_ACCESS_KEY_SECRET" not in child_env
    assert "USERPROFILE" not in child_env
    assert "RANDOM_SERVICE_TOKEN" not in child_env


def test_T006_secret_never_in_repr_log_or_json(caplog: pytest.LogCaptureFixture) -> None:
    secret = Secret("sk-proj-abcdefghijklmnopqrstuvwxyz")
    aliyun = Secret("LTAI5t6secretsecret")
    generic = Secret("ghp_abcdefghijklmnopqrstuvwxyz123456")
    provider = CredentialProvider(lambda name: {"llm": secret}[name])
    context = AgentContext(task_id="task-1", credential_provider=provider)

    assert provider.get_secret_value("llm") == "sk-proj-abcdefghijklmnopqrstuvwxyz"
    assert "sk-proj" not in repr(secret)
    assert "sk-proj" not in str(secret)
    assert "sk-proj" not in secret.model_dump_json()
    assert "sk-proj" not in repr(context)

    payload = {
        "openai": secret,
        "aliyun": aliyun,
        "generic": generic,
        "short": "sk-no",
    }
    encoded = json.dumps(payload, default=lambda value: value.to_json_safe())
    assert "sk-proj" not in encoded
    assert "LTAI5" not in encoded
    assert "ghp_" not in encoded
    assert "sk-no" in encoded

    message = (
        "openai=sk-proj-abcdefghijklmnopqrstuvwxyz "
        "aliyun=LTAI5t6secretsecret token=ghp_abcdefghijklmnopqrstuvwxyz123456 short=abc123"
    )
    redacted = redact_text(message)
    assert "sk-proj" not in redacted
    assert "LTAI5" not in redacted
    assert "ghp_" not in redacted
    assert "abc123" in redacted

    caplog.set_level(logging.INFO)
    logging.getLogger("se_mentor.security").info(redact_text(message))
    assert "sk-proj" not in caplog.text
    assert "[REDACTED:" in caplog.text

    exc = redact_exception(RuntimeError(message))
    assert "sk-proj" not in str(exc)
    assert "LTAI5" not in str(exc)

    with pytest.raises(RedactionError) as failed:
        redact_text(message, patterns=[None])  # type: ignore[list-item]
    assert "sk-proj" not in str(failed.value)
    assert "redaction failed" in str(failed.value)
