from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
from types import SimpleNamespace
from urllib import request as urlrequest

import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

APP_NAME = "SE-Mentor"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"--help", "-h"}:
        from se_mentor.cli.main import main as cli_main

        return cli_main(args)
    if args and args[0] in {"run", "credentials"}:
        if any(arg in {"--help", "-h"} for arg in args):
            from se_mentor.cli.main import main as cli_main

            return cli_main(args)
        _configure_packaged_runtime()
        from se_mentor.cli.main import main as cli_main

        return cli_main(args)
    if args and args[0] == "serve":
        args = args[1:]
    if args:
        from se_mentor.cli.main import main as cli_main

        return cli_main(args)
    return serve()


def serve() -> int:
    resource_root = _resource_root()
    runtime_root = _runtime_root()
    runtime_root.mkdir(parents=True, exist_ok=True)

    _configure_runtime(resource_root, runtime_root)

    host = os.environ.get("SE_MENTOR_HOST", DEFAULT_HOST)
    port = _port()
    app = _packaged_app(resource_root)
    url = f"http://{host}:{port}"
    print(f"SE-Mentor is starting at {url}")
    print(f"Runtime data: {runtime_root}")
    if os.environ.get("SE_MENTOR_NO_BROWSER") != "1":
        _open_browser_when_ready(f"{url}/health", url)

    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def _configure_packaged_runtime() -> None:
    resource_root = _resource_root()
    runtime_root = _runtime_root()
    runtime_root.mkdir(parents=True, exist_ok=True)
    _configure_runtime(resource_root, runtime_root)


def _configure_runtime(resource_root: Path, runtime_root: Path) -> None:
    os.environ.setdefault("SE_MENTOR_RUNTIME_PROFILE", "LOCAL_FULL")
    os.environ.setdefault("SE_MENTOR_RUNTIME_ROOT", str(runtime_root))
    os.environ.setdefault("SE_MENTOR_DATABASE_URL", _database_url(runtime_root))
    _upgrade_database(resource_root, os.environ["SE_MENTOR_DATABASE_URL"])


def _packaged_app(resource_root: Path) -> FastAPI:
    from se_mentor.main import create_app

    app = create_app()
    frontend_dir = _frontend_dir(resource_root)
    if not frontend_dir.is_dir():
        raise RuntimeError(f"frontend assets are missing: {frontend_dir}")
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    return app


def _upgrade_database(resource_root: Path, database_url: str) -> None:
    alembic_ini = resource_root / "alembic.ini"
    migrations = resource_root / "migrations"
    if not alembic_ini.is_file():
        raise RuntimeError(f"alembic.ini is missing: {alembic_ini}")
    if not migrations.is_dir():
        raise RuntimeError(f"migrations directory is missing: {migrations}")

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(migrations))
    config.set_main_option("sqlalchemy.url", database_url)
    config.cmd_opts = SimpleNamespace(x=[])
    command.upgrade(config, "head")


def _resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).resolve()
    return Path(__file__).resolve().parents[1]


def _frontend_dir(resource_root: Path) -> Path:
    configured = os.environ.get("SE_MENTOR_FRONTEND_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return resource_root / "frontend"


def _runtime_root() -> Path:
    configured = os.environ.get("SE_MENTOR_RUNTIME_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    if os.environ.get("SE_MENTOR_RUNTIME_PROFILE", "").upper() == "CLOUD_DEMO":
        demo_runtime = os.environ.get("SE_MENTOR_DEMO_RUNTIME_ROOT")
        if demo_runtime:
            return Path(demo_runtime).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_NAME
    return Path.home() / "AppData" / "Local" / APP_NAME


def _database_url(runtime_root: Path) -> str:
    return f"sqlite:///{runtime_root / 'se_mentor_api.sqlite3'}"


def _port() -> int:
    raw = os.environ.get("SE_MENTOR_PORT")
    if raw is None:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError("SE_MENTOR_PORT must be an integer") from exc
    if port <= 0 or port > 65535:
        raise RuntimeError("SE_MENTOR_PORT must be between 1 and 65535")
    return port


def _open_browser_when_ready(health_url: str, app_url: str) -> None:
    thread = threading.Thread(
        target=_open_browser_worker,
        args=(health_url, app_url),
        daemon=True,
    )
    thread.start()


def _open_browser_worker(health_url: str, app_url: str) -> None:
    for _ in range(30):
        try:
            with urlrequest.urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(app_url)
                    return
        except OSError:
            time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
