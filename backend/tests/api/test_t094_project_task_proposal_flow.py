from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient

from se_mentor.llm.base import LLMRequest, LLMResponse, LLMUsage
from se_mentor.main import create_app


class StructuredProvider:
    provider_name = "recording"
    model = "recording"

    def complete(self, request: LLMRequest) -> LLMResponse:
        if "impact" in request.prompt_summary.lower():
            data = json.loads(request.input_text)
            content = json.dumps(
                {
                    "fact_refs": data["evidence_ids"],
                    "narrative": "治理结果来自后端影响分析。",
                    "risks": data["unknowns"],
                },
                sort_keys=True,
            )
        else:
            content = json.dumps(
                {
                    "goal": "change app",
                    "understanding": "User wants app.py changed.",
                    "expected_behavior": "app.py reflects the requested change.",
                    "scope": ["app.py"],
                    "changes": [
                        {
                            "path": "app.py",
                            "symbol": None,
                            "action": "Change app behavior.",
                            "reason": "app.py is an evidenced repository path.",
                        }
                    ],
                    "steps": ["Read app.py", "Apply the requested change"],
                    "non_goals": [],
                    "constraints": ["Use evidenced paths from context."],
                    "acceptance": ["app.py is reviewed."],
                    "validation": ["Run relevant backend checks."],
                    "user_facts": ["User asked to change app."],
                    "inferences": ["app.py is the target file."],
                    "risks": ["No known high-risk paths."],
                },
                sort_keys=True,
            )
        return LLMResponse(
            content=content,
            usage=LLMUsage(10, 10),
            model=self.model,
            provider=self.provider_name,
        )


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=path, check=True)
    (path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)
    return path


def test_T094_project_task_list_and_proposal_review_contract(tmp_path: Path, monkeypatch) -> None:
    provider = StructuredProvider()
    monkeypatch.setattr("se_mentor.api.proposals.get_domain_provider", lambda: provider)
    client = TestClient(create_app())
    repo = _git_repo(tmp_path / "repo")

    project = client.post("/api/projects", json={"rootPath": str(repo)}).json()["data"]
    for _ in range(20):
        bootstrap = client.get(f"/api/projects/{project['id']}/bootstrap").json()["data"]
        if bootstrap["status"] == "READY":
            break
        time.sleep(0.1)
    task = client.post(
        "/api/tasks",
        json={"projectId": project["id"], "request": "change app"},
    ).json()["data"]
    proposal_v1 = client.post(
        f"/api/tasks/{task['id']}/proposals",
        json={
            "goal": "change app",
            "missingInformationQuestion": "Which module should change?",
        },
    ).json()["data"]

    tasks = client.get(f"/api/projects/{project['id']}/tasks")
    current = client.get(f"/api/tasks/{task['id']}/proposals")
    adjusted = client.post(
        f"/api/tasks/{task['id']}/proposals/{proposal_v1['id']}/adjust",
        json={"instruction": "change user module only"},
    )
    confirmed = client.post(
        f"/api/tasks/{task['id']}/proposals/{adjusted.json()['data']['id']}/confirm",
    )
    missing_adjustment = client.post(
        f"/api/tasks/{task['id']}/proposals/{proposal_v1['id']}/adjust",
        json={"instruction": ""},
    )

    assert tasks.status_code == 200
    assert project["rootPath"] == str(repo.resolve())
    assert tasks.json()["data"]["items"][0]["id"] == task["id"]
    assert current.status_code == 200
    assert current.json()["data"]["missingInformationQuestion"] is None
    assert adjusted.status_code == 201
    assert adjusted.json()["data"]["version"] == 2
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["status"] == "CONFIRMED"
    assert missing_adjustment.status_code == 400
    assert missing_adjustment.json()["error"]["code"] == "PROPOSAL_ADJUSTMENT_REQUIRED"
