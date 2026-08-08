from __future__ import annotations

import json
from pathlib import Path

from phase1_test_helpers import create_schema

from se_mentor.config.schema import PolicyValue
from se_mentor.db.session import create_session_factory, session_scope
from se_mentor.models.project import Project, ProjectConfig
from se_mentor.projects.config_service import (
    ConfigExecutionGate,
    compute_project_effective_config,
)


def test_AC_FR01_02_more_restrictive_config_wins_and_missing_required_blocks_task(
    tmp_path: Path,
) -> None:
    engine = create_schema(tmp_path / "config.sqlite3")
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        project = Project(root_path=str(tmp_path / "repo"))
        session.add(project)
        session.flush()
        session.add(
            ProjectConfig(
                project_id=project.id,
                version=1,
                effective_scope="project",
                config_json=json.dumps(
                    {
                        "shell_policy": "ALLOW",
                        "network_policy": "ALLOW",
                        "allow_arbitrary_repo_paths": True,
                        "llm_provider": "configured",
                    }
                ),
            )
        )
        session.flush()
        effective = compute_project_effective_config(
            session,
            project.id,
            profile="CLOUD_DEMO",
            task_values={"allow_repository_upload": True},
        )

    assert effective.values["shell_policy"] is PolicyValue.DENY_HARD
    assert effective.values["network_policy"] is PolicyValue.DENY_HARD
    assert effective.values["llm_provider"] == "mock"
    assert effective.hash
    assert effective.sources["shell_policy"] == "profile:CLOUD_DEMO"
    assert "attempted to relax" in effective.explain("shell_policy")

    blocked = ConfigExecutionGate(required_keys=("llm_provider", "approval_policy")).evaluate(
        effective
    )
    assert blocked.can_start_task is False
    assert blocked.reason == "MISSING_REQUIRED_CONFIG"
    assert blocked.missing_keys == ("approval_policy",)
