from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib import parse as urlparse

ONLINE_SAFE_PROVIDER_CREDENTIAL_REQUIRED = "ONLINE_SAFE_PROVIDER_CREDENTIAL_REQUIRED"
ONLINE_SAFE_PROVIDER_ENDPOINT_INVALID = "ONLINE_SAFE_PROVIDER_ENDPOINT_INVALID"
ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN = "ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN"
ONLINE_SAFE_PROVIDER_ENDPOINT_RESOLUTION_FAILED = "ONLINE_SAFE_PROVIDER_ENDPOINT_RESOLUTION_FAILED"
ONLINE_SAFE_PROVIDER_TRANSPORT_REQUIRED = "ONLINE_SAFE_PROVIDER_TRANSPORT_REQUIRED"


class OnlineProviderEndpointError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OnlineProviderEndpoint:
    base_url: str
    hostname: str
    port: int | None
    resolved_addresses: tuple[str, ...]


AddressInfoResolver = Callable[
    [str, int | None, int, int, int, int],
    list[tuple[int, int, int, str, tuple[object, ...]]],
]


class OnlineProviderEndpointPolicy:
    def __init__(self, resolver: AddressInfoResolver | None = None) -> None:
        self._resolver = resolver or socket.getaddrinfo

    def validate(self, base_url: str) -> OnlineProviderEndpoint:
        normalized = _normalize_base_url(base_url)
        parsed = urlparse.urlparse(normalized)
        hostname = parsed.hostname
        if parsed.scheme != "https":
            raise OnlineProviderEndpointError(
                ONLINE_SAFE_PROVIDER_TRANSPORT_REQUIRED,
                "ONLINE_SAFE provider base_url must use HTTPS",
            )
        if parsed.username or parsed.password:
            raise OnlineProviderEndpointError(
                ONLINE_SAFE_PROVIDER_ENDPOINT_INVALID,
                "ONLINE_SAFE provider base_url must not include URL credentials",
            )
        if not hostname:
            raise OnlineProviderEndpointError(
                ONLINE_SAFE_PROVIDER_ENDPOINT_INVALID,
                "ONLINE_SAFE provider base_url must include a hostname",
            )
        try:
            port = parsed.port
        except ValueError as exc:
            raise OnlineProviderEndpointError(
                ONLINE_SAFE_PROVIDER_ENDPOINT_INVALID,
                "ONLINE_SAFE provider base_url includes an invalid port",
            ) from exc
        if _is_localhost_name(hostname):
            raise OnlineProviderEndpointError(
                ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN,
                "ONLINE_SAFE provider hostname is not public",
            )
        resolved = _resolved_addresses(hostname, port, resolver=self._resolver)
        for address in resolved:
            _validate_public_address(address)
        return OnlineProviderEndpoint(
            base_url=normalized,
            hostname=hostname.lower().rstrip("."),
            port=port,
            resolved_addresses=tuple(resolved),
        )


def validate_online_provider_endpoint(base_url: str) -> OnlineProviderEndpoint:
    return OnlineProviderEndpointPolicy().validate(base_url)


def _normalize_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")].rstrip("/")
    if not normalized:
        raise OnlineProviderEndpointError(
            ONLINE_SAFE_PROVIDER_ENDPOINT_INVALID,
            "ONLINE_SAFE provider base_url is required",
        )
    return normalized


def _resolved_addresses(
    hostname: str,
    port: int | None,
    *,
    resolver: AddressInfoResolver,
) -> tuple[str, ...]:
    if literal := _ip_literal(hostname):
        return (str(literal),)
    try:
        infos = resolver(hostname, port or 443, 0, socket.SOCK_STREAM, 0, 0)
    except OSError as exc:
        raise OnlineProviderEndpointError(
            ONLINE_SAFE_PROVIDER_ENDPOINT_RESOLUTION_FAILED,
            "ONLINE_SAFE provider hostname resolution failed",
        ) from exc
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        address = sockaddr[0]
        if isinstance(address, str) and address not in addresses:
            addresses.append(address)
    if not addresses:
        raise OnlineProviderEndpointError(
            ONLINE_SAFE_PROVIDER_ENDPOINT_RESOLUTION_FAILED,
            "ONLINE_SAFE provider hostname resolution returned no addresses",
        )
    return tuple(addresses)


def _ip_literal(hostname: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return None


def _validate_public_address(address: str) -> None:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise OnlineProviderEndpointError(
            ONLINE_SAFE_PROVIDER_ENDPOINT_RESOLUTION_FAILED,
            "ONLINE_SAFE provider hostname resolved to an invalid address",
        ) from exc
    if parsed.is_global:
        return
    raise OnlineProviderEndpointError(
        ONLINE_SAFE_PROVIDER_ENDPOINT_FORBIDDEN,
        "ONLINE_SAFE provider hostname resolved to a non-public address",
    )


def _is_localhost_name(hostname: str) -> bool:
    lowered = hostname.lower().rstrip(".")
    return lowered == "localhost" or lowered.endswith(".localhost")
