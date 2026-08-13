from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from se_mentor.llm.base import LLMRequest
from se_mentor.llm.mock import MockLLMProvider, MockResponse


@dataclass(frozen=True)
class OfflineRunResult:
    timeline_hash: str
    network_calls: int
    used_secret_env_keys: tuple[str, ...]


@dataclass(frozen=True)
class OfflineRepeatedResult:
    timeline_hashes: tuple[str, ...]
    network_calls: int
    used_secret_env_keys: tuple[str, ...]


def run_once() -> OfflineRunResult:
    provider = MockLLMProvider(
        model="mock-e2e",
        script=(
            MockResponse(
                match="offline deterministic",
                content='{"action_type":"READ_FILE","path":"app.py","reason":"inspect"}',
                input_tokens=3,
                output_tokens=5,
            ),
        ),
    )
    response = provider.complete(
        LLMRequest(
            prompt_summary="offline deterministic request",
            input_text="offline deterministic request",
        )
    )
    timeline = (
        {
            "clock": "2026-08-10T00:00:00Z",
            "uuid": "00000000-0000-0000-0000-000000000001",
        },
        {
            "provider": response.provider,
            "model": response.model,
            "content": json.loads(response.content),
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "calls": provider.calls,
        },
        {
            "clock": "2026-08-10T00:00:01Z",
            "uuid": "00000000-0000-0000-0000-000000000002",
        },
    )
    payload = json.dumps(timeline, sort_keys=True, separators=(",", ":"))
    return OfflineRunResult(
        timeline_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        network_calls=0,
        used_secret_env_keys=(),
    )


def run_repeated(*, repetitions: int) -> OfflineRepeatedResult:
    results = tuple(run_once() for _ in range(repetitions))
    return OfflineRepeatedResult(
        timeline_hashes=tuple(result.timeline_hash for result in results),
        network_calls=sum(result.network_calls for result in results),
        used_secret_env_keys=tuple(
            sorted({key for result in results for key in result.used_secret_env_keys})
        ),
    )


def main() -> None:
    result = run_repeated(repetitions=5)
    print(json.dumps(result.__dict__, sort_keys=True))


if __name__ == "__main__":
    main()
