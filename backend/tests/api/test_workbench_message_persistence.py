from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from se_mentor.api.runtime import get_session_factory
from se_mentor.api.workbench_presentation import workbench_message_text
from se_mentor.db.session import session_scope
from se_mentor.llm.base import LLMRequest, LLMResponse, LLMUsage
from se_mentor.main import create_app
from se_mentor.models.task import (
    ChangeProposal,
    ProposalCompleteness,
    ProposalCreatedByType,
    ProposalStatus,
)


def test_workbench_messages_persist_and_reload_in_sequence(tmp_path: Path) -> None:
    client = TestClient(create_app())
    repo = _git_repo(tmp_path / "repo")
    project = client.post("/api/projects", json={"rootPath": str(repo)}).json()["data"]
    task = client.post(
        "/api/tasks",
        json={"projectId": project["id"], "request": "新增个人主页"},
    ).json()["data"]

    client.post(
        f"/api/tasks/{task['id']}/messages",
        json={
            "role": "USER",
            "kind": "TEXT",
            "status": "DONE",
            "text": "昵称不能重复",
        },
    )
    client.post(
        f"/api/tasks/{task['id']}/messages",
        json={
            "role": "MENTOR",
            "kind": "ERROR",
            "status": "ERROR",
            "text": "方案调整失败：模型服务超时。",
        },
    )

    reloaded = client.get(f"/api/tasks/{task['id']}/messages")

    assert reloaded.status_code == 200
    items = reloaded.json()["data"]["items"]
    assert [item["sequence"] for item in items] == [1, 2, 3]
    assert [item["role"] for item in items] == ["USER", "USER", "MENTOR"]
    assert [item["text"] for item in items] == [
        "新增个人主页",
        "昵称不能重复",
        "方案调整失败：模型服务超时。",
    ]


def test_mentor_turn_question_persists_answer_without_creating_proposal(tmp_path: Path) -> None:
    client = TestClient(create_app())
    repo = _git_repo(tmp_path / "repo")
    project = client.post("/api/projects", json={"rootPath": str(repo)}).json()["data"]
    task = client.post(
        "/api/tasks",
        json={"projectId": project["id"], "request": "新增个人主页"},
    ).json()["data"]
    proposal_id = _seed_proposal(task["id"])

    response = client.post(
        f"/api/tasks/{task['id']}/turns",
        json={"text": "还有什么待分析影响？"},
    )

    assert response.status_code == 201
    assert response.json()["data"]["type"] == "ANSWER"
    messages = client.get(f"/api/tasks/{task['id']}/messages").json()["data"]["items"]
    assert [message["role"] for message in messages] == ["USER", "USER", "MENTOR"]
    assert messages[-1]["kind"] == "TEXT"
    assert client.get(f"/api/tasks/{task['id']}/proposals").json()["data"]["id"] == proposal_id


def test_mentor_turn_question_answer_input_keeps_current_user_query(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    class CapturingProvider:
        provider_name = "test"
        model = "test-model"

        def complete(self, request: LLMRequest) -> LLMResponse:
            captured["prompt"] = request.input_text
            return LLMResponse(
                content="项目记忆会展示知识条目、项目理解、关键路径和证据引用，并学习已验证的工程模式与经验。",
                usage=LLMUsage(input_tokens=1, output_tokens=1),
                model=self.model,
                provider=self.provider_name,
            )

    monkeypatch.setattr(
        "se_mentor.api.mentor_turns.get_domain_provider", lambda: CapturingProvider()
    )
    client = TestClient(create_app())
    repo = _git_repo(tmp_path / "repo")
    project = client.post("/api/projects", json={"rootPath": str(repo)}).json()["data"]
    task = client.post(
        "/api/tasks",
        json={"projectId": project["id"], "request": "调整当前 Proposal 的卡片展示"},
    ).json()["data"]
    proposal_id = _seed_proposal(task["id"])
    current_query = "我的项目记忆功能到底能展示什么，学习什么？"

    response = client.post(f"/api/tasks/{task['id']}/turns", json={"text": current_query})

    assert response.status_code == 201
    assert response.json()["data"]["type"] == "ANSWER"
    assert f"CURRENT USER QUESTION:\n{current_query}" in captured["prompt"]
    assert (
        "Do not replace the user's question with the current proposal topic." in captured["prompt"]
    )
    assert "[memory] 项目记忆功能" in captured["prompt"]
    proposals = client.get(f"/api/tasks/{task['id']}/proposals/history").json()["data"]["items"]
    assert [proposal["version"] for proposal in proposals] == [1]
    assert proposals[0]["id"] == proposal_id


def test_mentor_turn_question_persists_answer_field_not_structured_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class StructuredProvider:
        provider_name = "test"
        model = "test-model"

        def complete(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                content='{"answer":"还有 5 类影响需要继续分析。"}',
                usage=LLMUsage(input_tokens=1, output_tokens=1),
                model=self.model,
                provider=self.provider_name,
            )

    monkeypatch.setattr(
        "se_mentor.api.mentor_turns.get_domain_provider", lambda: StructuredProvider()
    )
    client = TestClient(create_app())
    repo = _git_repo(tmp_path / "repo")
    project = client.post("/api/projects", json={"rootPath": str(repo)}).json()["data"]
    task = client.post(
        "/api/tasks",
        json={"projectId": project["id"], "request": "新增个人主页"},
    ).json()["data"]
    _seed_proposal(task["id"])

    response = client.post(
        f"/api/tasks/{task['id']}/turns",
        json={"text": "还有哪些影响没有分析？"},
    )

    assert response.status_code == 201
    messages = client.get(f"/api/tasks/{task['id']}/messages").json()["data"]["items"]
    text = messages[-1]["text"]
    assert text == "还有 5 类影响需要继续分析。"
    assert "answer" not in text
    assert "{" not in text
    assert "}" not in text


def test_structured_results_are_mapped_at_workbench_presentation_boundary() -> None:
    assert (
        workbench_message_text(
            role="MENTOR",
            kind="TEXT",
            text='```json\n{"answer":"More impacts remain:\\n\\n1. **Performance**"}\n```',
        )
        == "More impacts remain:\n\n1. **Performance**"
    )
    assert (
        workbench_message_text(
            role="MENTOR",
            kind="TEXT",
            text='{"answer":"还有三个影响需要深入核实。"}',
        )
        == "还有三个影响需要深入核实。"
    )
    proposal_text = workbench_message_text(
        role="MENTOR",
        kind="PROPOSAL",
        text='{"proposal":{"version":"v1","goal":"bad authority"}}',
    )
    assert proposal_text == "我已经更新了当前方案，请查看下方 Proposal 卡片。"
    assert "proposal" not in proposal_text
    assert "{" not in proposal_text
    assert (
        workbench_message_text(
            role="MENTOR",
            kind="ERROR",
            text='{"message":"模型返回的方案格式不完整，请重新生成。"}',
        )
        == "模型返回的方案格式不完整，请重新生成。"
    )


def test_continue_analysis_turn_stays_answer_without_new_proposal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class StructuredProvider:
        provider_name = "test"
        model = "test-model"

        def complete(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                content='{"proposal":{"version":"v1","goal":"should not leak"}}',
                usage=LLMUsage(input_tokens=1, output_tokens=1),
                model=self.model,
                provider=self.provider_name,
            )

    monkeypatch.setattr(
        "se_mentor.api.mentor_turns.get_domain_provider", lambda: StructuredProvider()
    )
    client = TestClient(create_app())
    repo = _git_repo(tmp_path / "repo")
    project = client.post("/api/projects", json={"rootPath": str(repo)}).json()["data"]
    task = client.post(
        "/api/tasks",
        json={"projectId": project["id"], "request": "新增个人主页"},
    ).json()["data"]
    proposal_id = _seed_proposal(task["id"])

    response = client.post(f"/api/tasks/{task['id']}/turns", json={"text": "那你继续分析。"})

    assert response.status_code == 201
    assert response.json()["data"]["type"] == "ANSWER"
    messages = client.get(f"/api/tasks/{task['id']}/messages").json()["data"]["items"]
    text = messages[-1]["text"]
    assert messages[-1]["kind"] == "TEXT"
    assert "proposal" not in text
    assert "{" not in text
    assert "}" not in text
    proposals = client.get(f"/api/tasks/{task['id']}/proposals/history").json()["data"]["items"]
    assert [proposal["version"] for proposal in proposals] == [1]
    assert proposals[0]["id"] == proposal_id


def test_mentor_turn_question_persists_fenced_answer_as_markdown_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FencedStructuredProvider:
        provider_name = "test"
        model = "test-model"

        def complete(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                content=(
                    "```json\n"
                    '{"answer":"More impacts remain:\\n\\n1. **Performance**\\n2. **Security**"}\n'
                    "```"
                ),
                usage=LLMUsage(input_tokens=1, output_tokens=1),
                model=self.model,
                provider=self.provider_name,
            )

    monkeypatch.setattr(
        "se_mentor.api.mentor_turns.get_domain_provider", lambda: FencedStructuredProvider()
    )
    client = TestClient(create_app())
    repo = _git_repo(tmp_path / "repo")
    project = client.post("/api/projects", json={"rootPath": str(repo)}).json()["data"]
    task = client.post(
        "/api/tasks",
        json={"projectId": project["id"], "request": "add profile page"},
    ).json()["data"]
    _seed_proposal(task["id"])

    response = client.post(
        f"/api/tasks/{task['id']}/turns",
        json={"text": "What impacts remain unanalyzed?"},
    )

    assert response.status_code == 201
    messages = client.get(f"/api/tasks/{task['id']}/messages").json()["data"]["items"]
    text = messages[-1]["text"]
    assert text == "More impacts remain:\n\n1. **Performance**\n2. **Security**"
    assert "answer" not in text
    assert "```json" not in text
    assert "\\n" not in text


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tests"], cwd=path, check=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)
    return path


def _seed_proposal(task_id: str) -> str:
    with session_scope(get_session_factory()) as session:
        proposal = ChangeProposal(
            task_id=task_id,
            version=1,
            goal="新增个人主页",
            current_problem='{"understanding":"需要新增个人主页"}',
            expected_behavior="用户可以查看个人主页",
            initial_scope_json='["src/profile.py"]',
            excluded_scope_json="[]",
            constraints_json='{"changes":[],"steps":["实现页面"],"constraints":[]}',
            assumptions_json="{}",
            risks_json='{"risks":["UNKNOWN"],"inferences":[]}',
            acceptance_criteria_json='["页面可访问"]',
            validation_plan_json='["运行相关测试"]',
            completeness=ProposalCompleteness.COMPLETE,
            status=ProposalStatus.DRAFT,
            created_by_type=ProposalCreatedByType.LLM,
        )
        session.add(proposal)
        session.flush()
        proposal_id = proposal.id
    return proposal_id
