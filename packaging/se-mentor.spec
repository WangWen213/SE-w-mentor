# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata


ROOT = Path(SPECPATH).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND_DIST = ROOT / "frontend" / "dist"
MIGRATIONS = BACKEND / "migrations"
ALEMBIC_INI = BACKEND / "alembic.ini"
DEMO_WORKSPACE = ROOT / "deploy" / "demo-workspace"

datas = [
    (str(FRONTEND_DIST), "frontend"),
    (str(MIGRATIONS), "migrations"),
    (str(ALEMBIC_INI), "."),
    (str(DEMO_WORKSPACE), "deploy/demo-workspace"),
]
datas += copy_metadata("fastapi")
datas += copy_metadata("pydantic")
datas += copy_metadata("sqlalchemy")
datas += copy_metadata("uvicorn")
datas += copy_metadata("alembic")

hiddenimports = []
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("alembic")
hiddenimports += [
    "se_mentor.models",
    "uvicorn.lifespan.on",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
]

a = Analysis(
    [str(ROOT / "packaging" / "se_mentor_launcher.py")],
    pathex=[str(BACKEND / "src"), str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "mypy",
        "pytest",
        "ruff",
        "frontend.node_modules",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="se-mentor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SE-Mentor",
)
