from __future__ import annotations

import json
from collections.abc import Iterable

from se_mentor.security.prompt_boundary import IsolatedRepositoryText


def build_system_prompt(
    *,
    system_policy: dict[str, object],
    execution_policy: dict[str, object],
    untrusted_repository_sections: Iterable[IsolatedRepositoryText],
) -> str:
    lines = [
        "SYSTEM_POLICY",
        json.dumps(system_policy, sort_keys=True),
        "EXECUTION_POLICY",
        json.dumps(execution_policy, sort_keys=True),
    ]
    for section in untrusted_repository_sections:
        lines.extend(
            [
                f"BEGIN_{section.label}",
                f"source={section.source_ref}",
                section.text,
                f"END_{section.label}",
            ]
        )
    return "\n".join(lines)
