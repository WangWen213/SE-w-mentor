from __future__ import annotations

import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

ONLINE_SESSION_COOKIE = "se_mentor_session"
AUTHORIZED_TARGET = "src/sample/text_utils.py"
UNAUTHORIZED_TARGET = "src/sample/unauthorized.py"


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    input_tokens: int = 10
    output_tokens: int = 10


class ControlledOpenAIProvider:
    provider_name = "openai"
    model = "controlled-online-safe-e2e"

    def __init__(self) -> None:
        self.proposal_calls = 0
        self.impact_calls = 0
        self.execution_calls = 0

    def complete(self, request):
        from se_mentor.llm.base import LLMResponse, LLMUsage
        from se_mentor.llm.prompts.impact import IMPACT_REPORT_PROMPT_SUMMARY

        if request.prompt_summary in {
            "structured change proposal",
            "structured technical proposal supplement",
        }:
            self.proposal_calls += 1
            response = ProviderResponse(_proposal_content())
        elif request.prompt_summary == IMPACT_REPORT_PROMPT_SUMMARY:
            self.impact_calls += 1
            response = ProviderResponse(
                json.dumps(
                    {
                        "fact_refs": [],
                        "narrative": "发现 0 个现有受影响文件；授权 1 个计划创建路径。",
                        "risks": [],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        elif (
            "You are executing an already confirmed coding change."
            in request.input_text
        ):
            self.execution_calls += 1
            response = ProviderResponse(_execution_content(self.execution_calls))
        else:
            raise AssertionError(
                f"unexpected provider request: {request.prompt_summary}"
            )
        return LLMResponse(
            content=response.content,
            usage=LLMUsage(response.input_tokens, response.output_tokens),
            model=self.model,
            provider=self.provider_name,
        )

    def record_usage(
        self,
        session: Session,
        *,
        iteration_id: str,
        response,
        request_summary: str,
    ):
        from se_mentor.models.llm import LLMCall, LLMCallStatus, ParseStatus

        call = LLMCall(
            iteration_id=iteration_id,
            provider_name=self.provider_name,
            model_name=self.model,
            request_summary=request_summary,
            response_summary=f"{len(response.content)} chars",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            compression_count=0,
            status=LLMCallStatus.SUCCESS,
            retry_count=0,
            latency_ms=None,
            error_code=None,
            parse_status=ParseStatus.VALID,
        )
        session.add(call)
        session.flush()
        return call


def main() -> int:
    runtime_root = Path(tempfile.mkdtemp(prefix="se-mentor-online-safe-e2e-"))
    try:
        provider = ControlledOpenAIProvider()
        app_module, runtime_module = _load_online_safe_app(runtime_root, provider)
        port = _free_port()
        server = uvicorn.Server(
            uvicorn.Config(
                app_module.create_app(),
                host="127.0.0.1",
                port=port,
                log_level="warning",
            )
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{port}"
        _wait_health(base_url, server=server, thread=thread)
        try:
            result = _run_http_flow(base_url, runtime_module)
        finally:
            server.should_exit = True
            thread.join(timeout=10)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)


def _run_http_flow(base_url: str, runtime_module) -> dict[str, Any]:
    client = _SessionClient(base_url)
    project = client.post_zip("/api/projects/import-zip", _project_zip())["data"]
    project_id = str(project["id"])
    client.post_json(
        "/api/credentials/llm",
        {
            "provider": "openai-compatible",
            "key": "test-online-safe-provider-key",
            "baseUrl": "https://93.184.216.34/v1",
            "model": "controlled-online-safe-e2e",
        },
    )
    _wait_bootstrap(client, project_id)

    success = _run_task(client, "create normalize_name helper")
    reloaded = client.get_json(f"/api/proposals/{success['proposal_id']}/governance")
    _assert_no_error(reloaded)
    execute = client.post_json(
        f"/api/tasks/{success['task_id']}/execute",
        {"command": "APPLY_APPROVED_CHANGES"},
    )
    _assert_no_error(execute)
    if execute["data"]["status"] != "COMPLETED":
        raise AssertionError(f"execution did not complete: {execute}")

    project_root = _project_root(runtime_module, project_id)
    created = project_root / AUTHORIZED_TARGET
    content = created.read_text(encoding="utf-8")
    if "def normalize_name(name: str) -> str:" not in content:
        raise AssertionError("normalize_name implementation was not created")
    if '" ".join(name.strip().split()).title()' not in content:
        raise AssertionError("normalize_name content is incomplete")
    git_status = _git_status(project_root)
    if AUTHORIZED_TARGET not in git_status:
        raise AssertionError(
            f"git status does not include created file: {git_status!r}"
        )

    denied = _run_task(client, "attempt unauthorized create")
    client.get_json(f"/api/proposals/{denied['proposal_id']}/governance")
    denied_execute = client.post_json(
        f"/api/tasks/{denied['task_id']}/execute",
        {"command": "APPLY_APPROVED_CHANGES"},
        expect_ok=False,
    )
    if denied_execute["error"] is None:
        raise AssertionError("unauthorized execution unexpectedly succeeded")
    if (project_root / UNAUTHORIZED_TARGET).exists():
        raise AssertionError("unauthorized file was created")

    return {
        "authorized_target": AUTHORIZED_TARGET,
        "denied_error": denied_execute["error"]["message"],
        "git_status": git_status,
        "project_root": str(project_root),
        "result": "PASS",
    }


def _run_task(client: _SessionClient, request_text: str) -> dict[str, str]:
    task = client.post_json(
        "/api/tasks",
        {"projectId": client.project_id, "request": request_text},
        expected_status=201,
    )["data"]
    task_id = str(task["id"])
    proposal = client.post_json(
        f"/api/tasks/{task_id}/proposals",
        {"goal": request_text},
        expected_status=201,
    )["data"]
    proposal_id = str(proposal["id"])
    confirmed = client.post_json(
        f"/api/tasks/{task_id}/proposals/{proposal_id}/confirm", {}
    )
    _assert_no_error(confirmed)
    return {"task_id": task_id, "proposal_id": proposal_id}


class _SessionClient:
    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=60, trust_env=False)
        self.cookie: str | None = None
        self.project_id = ""

    def get_json(self, path: str, *, expect_ok: bool = True) -> dict[str, Any]:
        response = self.client.get(path, headers=self._headers())
        return self._json(response, expect_ok=expect_ok)

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        expected_status: int = 200,
        expect_ok: bool = True,
    ) -> dict[str, Any]:
        response = self.client.post(path, json=payload, headers=self._headers())
        data = self._json(
            response, expected_status=expected_status, expect_ok=expect_ok
        )
        if path == "/api/tasks" and data.get("data"):
            self.project_id = str(payload["projectId"])
        return data

    def post_zip(self, path: str, archive: bytes) -> dict[str, Any]:
        headers = {
            **self._headers(),
            "content-type": "application/zip",
            "x-se-mentor-filename": "sampleproject.zip",
        }
        response = self.client.post(path, content=archive, headers=headers)
        data = self._json(response, expected_status=201)
        self.project_id = str(data["data"]["id"])
        return data

    def _headers(self) -> dict[str, str]:
        headers = {"x-forwarded-proto": "https"}
        if self.cookie:
            headers["cookie"] = f"{ONLINE_SESSION_COOKIE}={self.cookie}"
        return headers

    def _json(
        self,
        response: httpx.Response,
        *,
        expected_status: int = 200,
        expect_ok: bool = True,
    ) -> dict[str, Any]:
        set_cookie = response.headers.get("set-cookie", "")
        if f"{ONLINE_SESSION_COOKIE}=" in set_cookie:
            self.cookie = set_cookie.split(f"{ONLINE_SESSION_COOKIE}=", 1)[1].split(
                ";", 1
            )[0]
        data = response.json()
        if expect_ok and response.status_code != expected_status:
            raise AssertionError(f"{response.status_code} != {expected_status}: {data}")
        if expect_ok:
            _assert_no_error(data)
        return data


def _load_online_safe_app(runtime_root: Path, provider: ControlledOpenAIProvider):
    demo_workspace = runtime_root / "demo-workspace"
    baseline = demo_workspace / ".baseline"
    baseline.mkdir(parents=True)
    (baseline / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(baseline, "init")
    _git(baseline, "config", "user.email", "test@example.invalid")
    _git(baseline, "config", "user.name", "SE Mentor Test")
    _git(baseline, "add", ".")
    _git(baseline, "commit", "-m", "baseline")

    os.environ["SE_MENTOR_RUNTIME_PROFILE"] = "ONLINE_SAFE"
    os.environ["SE_MENTOR_TRUST_PROXY"] = "true"
    os.environ["SE_MENTOR_RUNTIME_ROOT"] = str(runtime_root)
    os.environ["SE_MENTOR_DEMO_WORKSPACE"] = str(demo_workspace)
    os.environ["SE_MENTOR_DATABASE_URL"] = (
        f"sqlite:///{runtime_root / 'acceptance.sqlite3'}"
    )

    import se_mentor.api.credentials as credentials_api
    import se_mentor.api.execution as execution_api
    import se_mentor.api.governance as governance_api
    import se_mentor.api.online_readiness as online_readiness_api
    import se_mentor.api.projects as projects_api
    import se_mentor.api.proposals as proposals_api
    import se_mentor.api.runtime as runtime_module
    import se_mentor.api.runtime_workspace as runtime_workspace_api
    import se_mentor.api.tasks as tasks_api
    import se_mentor.main as app_module

    runtime_module = importlib.reload(runtime_module)
    runtime_module.build_openai_provider = lambda *args, **kwargs: provider
    importlib.reload(online_readiness_api)
    importlib.reload(projects_api)
    importlib.reload(credentials_api)
    importlib.reload(runtime_workspace_api)
    importlib.reload(tasks_api)
    importlib.reload(proposals_api)
    importlib.reload(governance_api)
    importlib.reload(execution_api)
    app_module = importlib.reload(app_module)
    return app_module, runtime_module


def _proposal_content() -> str:
    path = "./src//sample\\text_utils.py"
    return json.dumps(
        {
            "goal": "新增 normalize_name 工具函数",
            "understanding": "在 sample 包中新增一个名称规范化工具。",
            "expected_behavior": "normalize_name 会清理空格并按单词首字母大写。",
            "scope": [path],
            "changes": [
                {
                    "path": path,
                    "symbol": "normalize_name",
                    "action": "CREATE_FILE",
                    "reason": "用户要求新增 text_utils.py。",
                }
            ],
            "steps": ["创建 text_utils.py", "实现 normalize_name"],
            "non_goals": [],
            "constraints": ["只修改计划文件"],
            "acceptance": ["src/sample/text_utils.py 存在"],
            "validation": ["检查文件内容"],
            "user_facts": ["用户要求新增 normalize_name"],
            "inferences": ["这是一个单文件创建任务"],
            "risks": ["新增工具函数需要保持单一文件范围。"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _execution_content(call_number: int) -> str:
    if call_number == 1:
        path = "src\\sample\\text_utils.py"
        content = (
            "def normalize_name(name: str) -> str:\n"
            '    return " ".join(name.strip().split()).title()\n'
        )
    else:
        path = UNAUTHORIZED_TARGET
        content = "UNAUTHORIZED = True\n"
    return json.dumps(
        {
            "action_type": "CREATE_FILE",
            "parameters": {"path": path, "content": content},
            "reason": "Create requested helper file.",
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _project_zip() -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("pyproject.toml", '[project]\nname = "sampleproject"\n')
        archive.writestr("src/sample/__init__.py", "")
        archive.writestr(
            "src/sample/simple.py", "def existing() -> str:\n    return 'sample'\n"
        )
    return output.getvalue()


def _wait_bootstrap(client: _SessionClient, project_id: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        data = client.get_json(f"/api/projects/{project_id}/bootstrap")
        status = str(data["data"].get("status"))
        if status == "READY":
            return
        if status == "BOOTSTRAP_FAILED":
            raise AssertionError(f"bootstrap failed: {data}")
        time.sleep(0.25)
    raise AssertionError("bootstrap did not become READY")


def _wait_health(
    base_url: str, *, server: uvicorn.Server, thread: threading.Thread
) -> None:
    deadline = time.monotonic() + 30
    last_error = ""
    while time.monotonic() < deadline:
        if not thread.is_alive() and not server.started:
            raise AssertionError("backend server thread exited before startup")
        try:
            response = httpx.get(f"{base_url}/health", timeout=2, trust_env=False)
            if response.status_code == 200 and response.json() == {"status": "ok"}:
                return
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise AssertionError(f"backend did not become healthy: {last_error}")


def _project_root(runtime_module, project_id: str) -> Path:
    from se_mentor.models.project import Project

    with runtime_module.get_session_factory()() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise AssertionError("project not found in database")
        return Path(project.root_path)


def _git_status(project_root: Path) -> str:
    return subprocess.run(
        ["git", "status", "--short"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _assert_no_error(data: dict[str, Any]) -> None:
    if data.get("error") is not None:
        raise AssertionError(data)


if __name__ == "__main__":
    raise SystemExit(main())
