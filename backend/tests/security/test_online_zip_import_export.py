from __future__ import annotations

import importlib
import stat
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from se_mentor.git.git_service import GitService
from se_mentor.models.project import Project
from se_mentor.projects.bootstrap import ProjectBootstrapService
from se_mentor.runtime.online_sessions import (
    ONLINE_SESSION_COOKIE_NAME,
    InMemoryOnlineSessionStore,
)
from se_mentor.runtime.online_workspaces import (
    ONLINE_SAFE_WORKSPACE_ZIP_ERROR,
    SafeOnlineWorkspaceFactory,
)


def test_online_safe_imports_project_zip_into_current_session_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_module, runtime_module, projects_api = _reload_api_for_online_safe(
        monkeypatch,
        tmp_path / "runtime",
        _demo_workspace(tmp_path),
    )
    monkeypatch.setattr(
        projects_api,
        "_schedule_bootstrap",
        lambda project_id: {"status": "REGISTERED", "projectId": project_id},
    )
    client = TestClient(app_module.create_app(), base_url="https://testserver")
    archive = _zip_bytes(
        {
            "student-project/app.py": "print('hello')\n",
            "student-project/README.md": "coursework\n",
            "student-project/.env": "SECRET=1\n",
            "student-project/.git/config": "remote = leak\n",
            "student-project/private.pem": "secret\n",
        }
    )

    imported = client.post(
        "/api/projects/import-zip",
        content=archive,
        headers={"content-type": "application/zip", "x-se-mentor-filename": "project.zip"},
    )
    repeated = client.post(
        "/api/projects/import-zip",
        content=_zip_bytes({"other.py": "print('other')\n"}),
        headers={"content-type": "application/zip", "x-se-mentor-filename": "other.zip"},
    )
    listed = client.get("/api/projects")
    session_id = client.cookies.get(ONLINE_SESSION_COOKIE_NAME)

    with runtime_module.get_session_factory()() as session:
        project = session.get(Project, imported.json()["data"]["id"])
        assert project is not None
        project_root = Path(project.root_path)
        owner_hash = project.owner_session_hash

    assert imported.status_code == 201
    assert imported.json()["data"]["rootPath"] == "Uploaded Project"
    assert str(tmp_path) not in str(imported.json())
    assert session_id not in str(imported.json())
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "ONLINE_SAFE_PROJECT_ALREADY_EXISTS"
    assert listed.json()["data"]["items"][0]["id"] == imported.json()["data"]["id"]
    assert owner_hash is not None
    assert (project_root / "app.py").read_text(encoding="utf-8") == "print('hello')\n"
    assert not (project_root / ".env").exists()
    assert not (project_root / "private.pem").exists()
    assert not (project_root / ".git" / "config").read_text(encoding="utf-8").count("remote")
    assert not (project_root / "other.py").exists()
    assert GitService(project_root).status().modified == ()
    assert GitService(project_root).status().untracked == ()


def test_online_safe_zip_import_rejects_traversal_absolute_and_symlink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_module, _, _ = _reload_api_for_online_safe(
        monkeypatch,
        tmp_path / "runtime",
        _demo_workspace(tmp_path),
    )
    client = TestClient(app_module.create_app(), base_url="https://testserver")

    traversal = client.post("/api/projects/import-zip", content=_zip_bytes({"../x.py": "x"}))
    absolute = client.post("/api/projects/import-zip", content=_zip_bytes({"/x.py": "x"}))
    symlink = client.post("/api/projects/import-zip", content=_symlink_zip())

    assert traversal.status_code == 400
    assert traversal.json()["error"]["code"] == ONLINE_SAFE_WORKSPACE_ZIP_ERROR
    assert absolute.status_code == 400
    assert absolute.json()["error"]["code"] == ONLINE_SAFE_WORKSPACE_ZIP_ERROR
    assert symlink.status_code == 400
    assert symlink.json()["error"]["code"] == ONLINE_SAFE_WORKSPACE_ZIP_ERROR


def test_online_safe_import_enforces_zip_size_and_file_limits(tmp_path: Path) -> None:
    baseline = _demo_workspace(tmp_path) / ".baseline"
    factory = SafeOnlineWorkspaceFactory(
        runtime_root=tmp_path / "runtime",
        baseline_root=baseline,
        max_files=1,
    )
    session = InMemoryOnlineSessionStore().get_or_create(None)

    with pytest.raises(Exception) as exc:
        factory.import_zip(session, _zip_bytes({"a.py": "a", "b.py": "b"}))

    assert getattr(exc.value, "code", "") == "ONLINE_SAFE_WORKSPACE_LIMIT_EXCEEDED"


def test_online_safe_export_zip_and_patch_are_current_session_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_module, runtime_module, projects_api = _reload_api_for_online_safe(
        monkeypatch,
        tmp_path / "runtime",
        _demo_workspace(tmp_path),
    )
    monkeypatch.setattr(
        projects_api,
        "_schedule_bootstrap",
        lambda project_id: {"status": "REGISTERED", "projectId": project_id},
    )
    client_a = TestClient(app_module.create_app(), base_url="https://testserver")
    client_b = TestClient(app_module.create_app(), base_url="https://testserver")
    project_a = client_a.post(
        "/api/projects/import-zip",
        content=_zip_bytes({"app.py": "print('a')\n", ".env": "SECRET=1\n"}),
    ).json()["data"]
    project_b = client_b.post(
        "/api/projects/import-zip",
        content=_zip_bytes({"app.py": "print('b')\n"}),
    ).json()["data"]

    with runtime_module.get_session_factory()() as session:
        root_a = Path(session.get(Project, project_a["id"]).root_path)
        root_b = Path(session.get(Project, project_b["id"]).root_path)
    (root_a / "app.py").write_text("print('a changed')\n", encoding="utf-8")
    (root_a / "created.py").write_text("print('new')\n", encoding="utf-8")

    export_a = client_a.get(f"/api/projects/{project_a['id']}/export.zip")
    patch_with_untracked = client_a.get(f"/api/projects/{project_a['id']}/changes.patch")
    b_export_a = client_b.get(f"/api/projects/{project_a['id']}/export.zip")
    (root_a / "created.py").unlink()
    patch_a = client_a.get(f"/api/projects/{project_a['id']}/changes.patch")

    assert root_a != root_b
    assert export_a.status_code == 200
    with zipfile.ZipFile(BytesIO(export_a.content)) as exported:
        assert exported.read("app.py").decode("utf-8").replace("\r\n", "\n") == (
            "print('a changed')\n"
        )
        assert ".env" not in exported.namelist()
        assert not any(name.startswith(".git/") for name in exported.namelist())
    assert patch_with_untracked.status_code == 409
    assert patch_with_untracked.json()["error"]["code"].endswith("UNTRACKED_UNSUPPORTED")
    assert b_export_a.status_code == 404
    assert patch_a.status_code == 200
    assert "+print('a changed')" in patch_a.text


def test_imported_project_can_bootstrap_and_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app_module, runtime_module, projects_api = _reload_api_for_online_safe(
        monkeypatch,
        tmp_path / "runtime",
        _demo_workspace(tmp_path),
    )
    monkeypatch.setattr(
        projects_api,
        "_schedule_bootstrap",
        lambda project_id: {"status": "REGISTERED", "projectId": project_id},
    )
    client = TestClient(app_module.create_app(), base_url="https://testserver")
    project_id = client.post(
        "/api/projects/import-zip",
        content=_zip_bytes({"app.py": "def greet():\n    return 'hi'\n"}),
    ).json()["data"]["id"]

    with runtime_module.get_session_factory()() as session:
        bootstrap = ProjectBootstrapService(session).bootstrap(project_id)

    assert bootstrap.file_count == 1
    assert bootstrap.symbol_count >= 1
    assert bootstrap.modified_count == 0
    assert bootstrap.untracked_count == 0


def _zip_bytes(files: dict[str, str]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def _symlink_zip() -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo("link.py")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "target.py")
    return output.getvalue()


def _demo_workspace(tmp_path: Path) -> Path:
    demo_workspace = tmp_path / "demo-workspace"
    baseline = demo_workspace / ".baseline"
    baseline.mkdir(parents=True)
    (baseline / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=baseline, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=baseline,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "SE Mentor Test"],
        cwd=baseline,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=baseline, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "baseline"],
        cwd=baseline,
        check=True,
        capture_output=True,
    )
    return demo_workspace


def _reload_api_for_online_safe(
    monkeypatch: pytest.MonkeyPatch,
    runtime_root: Path,
    demo_workspace: Path,
):
    monkeypatch.setenv("SE_MENTOR_RUNTIME_PROFILE", "ONLINE_SAFE")
    monkeypatch.setenv("SE_MENTOR_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("SE_MENTOR_DEMO_WORKSPACE", str(demo_workspace))
    import se_mentor.api.credentials as credentials_api
    import se_mentor.api.online_readiness as online_readiness_api
    import se_mentor.api.projects as projects_api
    import se_mentor.api.runtime as runtime
    import se_mentor.api.runtime_workspace as runtime_workspace_api
    import se_mentor.main as main

    runtime = importlib.reload(runtime)
    importlib.reload(online_readiness_api)
    projects_api = importlib.reload(projects_api)
    credentials_api = importlib.reload(credentials_api)
    runtime_workspace_api = importlib.reload(runtime_workspace_api)
    main = importlib.reload(main)
    return main, runtime, projects_api
