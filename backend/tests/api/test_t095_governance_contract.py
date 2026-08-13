from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient

from se_mentor.llm.base import LLMRequest, LLMResponse, LLMUsage
from se_mentor.main import create_app


class RecordingProvider:
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
                    "goal": "调整认证逻辑",
                    "understanding": "用户希望更新认证中间件。",
                    "expected_behavior": "认证中间件按需求更新。",
                    "scope": ["auth/middleware.py"],
                    "changes": [
                        {
                            "path": "auth/middleware.py",
                            "symbol": None,
                            "action": "调整认证逻辑。",
                            "reason": "auth/middleware.py 是仓库中的真实路径。",
                        }
                    ],
                    "steps": ["读取认证中间件", "应用认证逻辑调整"],
                    "non_goals": [],
                    "constraints": [],
                    "acceptance": ["认证相关测试通过"],
                    "validation": ["运行认证相关测试"],
                    "user_facts": ["用户要求调整认证逻辑。"],
                    "inferences": ["认证中间件是变更目标。"],
                    "risks": ["Authentication behavior may require careful review."],
                },
                sort_keys=True,
            )
        return LLMResponse(
            content=content,
            usage=LLMUsage(10, 10),
            model=self.model,
            provider=self.provider_name,
        )


def test_T095_governance_exposes_facts_inference_unknowns_and_three_decisions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = RecordingProvider()
    monkeypatch.setattr("se_mentor.api.proposals.get_domain_provider", lambda: provider)
    monkeypatch.setattr("se_mentor.api.governance.get_domain_provider", lambda: provider)
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
        json={"projectId": project["id"], "request": "change auth"},
    ).json()["data"]
    proposal = client.post(
        f"/api/tasks/{task['id']}/proposals",
        json={"goal": "change auth"},
    ).json()["data"]
    client.post(f"/api/tasks/{task['id']}/proposals/{proposal['id']}/confirm")

    allow = client.post(
        f"/api/proposals/{proposal['id']}/governance",
        json={"changedPaths": ["src/user.py"]},
    )
    warn = client.post(
        f"/api/proposals/{proposal['id']}/governance",
        json={"changedPaths": ["auth/middleware.py"]},
    )
    block = client.post(
        f"/api/proposals/{proposal['id']}/governance",
        json={"changedPaths": [".env"]},
    )

    assert allow.json()["data"]["decision"] == "ALLOW"
    assert warn.json()["data"]["decision"] == "WARN"
    assert warn.json()["data"]["facts"]
    assert warn.json()["data"]["inferences"]
    assert warn.json()["data"]["unknowns"]
    assert warn.json()["data"]["evidence"]
    assert warn.json()["data"]["impactScope"]["summary"] == "1 \u4e2a\u6587\u4ef6\u53d7\u5f71\u54cd"
    assert warn.json()["data"]["ruleHits"][0]["level"] == "WARN"
    assert block.json()["data"]["decision"] == "BLOCK"
    assert block.json()["data"]["nonApprovable"] is True


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=path, check=True)
    (path / "auth").mkdir()
    (path / "auth" / "middleware.py").write_text("def auth():\n    return True\n", encoding="utf-8")
    (path / "src").mkdir()
    (path / "src" / "user.py").write_text("def user():\n    return True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)
    return path
