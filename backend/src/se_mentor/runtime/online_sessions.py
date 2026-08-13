from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from threading import Lock
from urllib import parse as urlparse

from se_mentor.security.secrets import Secret

ONLINE_SESSION_COOKIE_NAME = "se_mentor_session"
ONLINE_SESSION_ID_BYTES = 32
ONLINE_SESSION_TTL_SECONDS = 45 * 60
ONLINE_SESSION_MAX_ACTIVE = 128


class OnlineSessionRequired(RuntimeError):
    pass


class OnlineSessionExpired(RuntimeError):
    pass


class OnlineSessionLimitExceeded(RuntimeError):
    pass


class OnlineCredentialValidationError(ValueError):
    pass


@dataclass(frozen=True)
class OnlineCredentialMetadata:
    provider: str
    base_url: str
    model: str


@dataclass
class OnlineCredential:
    metadata: OnlineCredentialMetadata
    secret: Secret


@dataclass
class OnlineSession:
    session_id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    credential: OnlineCredential | None = None


class InMemoryOnlineSessionStore:
    def __init__(
        self,
        *,
        ttl_seconds: int = ONLINE_SESSION_TTL_SECONDS,
        max_active_sessions: int = ONLINE_SESSION_MAX_ACTIVE,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_active_sessions <= 0:
            raise ValueError("max_active_sessions must be positive")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max_active_sessions = max_active_sessions
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sessions: dict[str, OnlineSession] = {}
        self._lock = Lock()

    @property
    def ttl_seconds(self) -> int:
        return int(self._ttl.total_seconds())

    @property
    def max_active_sessions(self) -> int:
        return self._max_active_sessions

    @property
    def active_count(self) -> int:
        with self._lock:
            self._cleanup_locked(self._clock())
            return len(self._sessions)

    def get_or_create(self, session_id: str | None) -> OnlineSession:
        with self._lock:
            now = self._clock()
            self._cleanup_locked(now)
            if session_id:
                existing = self._sessions.get(session_id)
                if existing is not None:
                    if self._is_expired(existing, now):
                        self._sessions.pop(session_id, None)
                    else:
                        return self._touch_locked(existing, now)
            return self._create_locked(now)

    def require(self, session_id: str | None) -> OnlineSession:
        if not session_id:
            raise OnlineSessionRequired("ONLINE_SAFE session cookie is required")
        with self._lock:
            now = self._clock()
            existing = self._sessions.get(session_id)
            if existing is None:
                self._cleanup_locked(now)
                raise OnlineSessionRequired("ONLINE_SAFE session is missing")
            if self._is_expired(existing, now):
                self._sessions.pop(session_id, None)
                self._cleanup_locked(now)
                raise OnlineSessionExpired("ONLINE_SAFE session expired")
            self._cleanup_locked(now)
            return self._touch_locked(existing, now)

    def set_credential(
        self,
        session_id: str | None,
        *,
        provider: str,
        base_url: str,
        model: str,
        key: str,
    ) -> OnlineSession:
        session = self.require(session_id)
        metadata = validate_online_credential_metadata(
            provider=provider,
            base_url=base_url,
            model=model,
        )
        trimmed_key = key.strip()
        if not trimmed_key:
            raise OnlineCredentialValidationError("credential key is required")
        session.credential = OnlineCredential(metadata=metadata, secret=Secret(trimmed_key))
        return session

    def update_credential(
        self,
        session_id: str | None,
        *,
        provider: str,
        base_url: str,
        model: str,
        key: str | None,
    ) -> OnlineSession:
        session = self.require(session_id)
        metadata = validate_online_credential_metadata(
            provider=provider,
            base_url=base_url,
            model=model,
        )
        trimmed_key = key.strip() if key else ""
        if trimmed_key:
            session.credential = OnlineCredential(metadata=metadata, secret=Secret(trimmed_key))
        elif session.credential is None:
            raise OnlineSessionRequired("ONLINE_SAFE credential key is required")
        else:
            session.credential.metadata = metadata
        return session

    def clear_credential(self, session_id: str | None) -> OnlineSession:
        session = self.get_or_create(session_id)
        session.credential = None
        return session

    def credential_for(self, session_id: str | None) -> OnlineCredential | None:
        try:
            return self.require(session_id).credential
        except (OnlineSessionExpired, OnlineSessionRequired):
            return None

    def reset(self) -> None:
        with self._lock:
            self._sessions.clear()

    def _create_locked(self, now: datetime) -> OnlineSession:
        if len(self._sessions) >= self._max_active_sessions:
            raise OnlineSessionLimitExceeded("ONLINE_SAFE active session limit reached")
        session_id = token_urlsafe(ONLINE_SESSION_ID_BYTES)
        while session_id in self._sessions:
            session_id = token_urlsafe(ONLINE_SESSION_ID_BYTES)
        session = OnlineSession(
            session_id=session_id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + self._ttl,
        )
        self._sessions[session_id] = session
        return session

    def _touch_locked(self, session: OnlineSession, now: datetime) -> OnlineSession:
        session.last_seen_at = now
        session.expires_at = now + self._ttl
        return session

    def _cleanup_locked(self, now: datetime) -> None:
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if self._is_expired(session, now)
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)

    def _is_expired(self, session: OnlineSession, now: datetime) -> bool:
        return session.expires_at <= now


def validate_online_credential_metadata(
    *,
    provider: str,
    base_url: str,
    model: str,
) -> OnlineCredentialMetadata:
    provider_name = provider.strip()
    if provider_name.lower() not in {"openai", "openai-compatible"}:
        raise OnlineCredentialValidationError("only OpenAI provider is supported")
    normalized_base_url = _normalize_base_url(base_url)
    parsed = urlparse.urlparse(normalized_base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OnlineCredentialValidationError(
            "OpenAI-compatible base_url must include http(s) scheme and host"
        )
    model_name = model.strip()
    if not model_name:
        raise OnlineCredentialValidationError("model is required")
    return OnlineCredentialMetadata(
        provider="OpenAI",
        base_url=normalized_base_url,
        model=model_name,
    )


def _normalize_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")].rstrip("/")
    if not normalized:
        raise OnlineCredentialValidationError("base_url is required")
    return normalized
