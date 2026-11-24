# -*- mode: python ; coding: utf-8 -*-
# Receta de PyInstaller para el backend de CONTADOR AI.
# Uso (desde backend/):  .venv/bin/pyinstaller packaging/contador-backend.spec --noconfirm
# Resultado: dist/contador-backend/ (modo carpeta: arranca más rápido que un único
# archivo y genera menos falsos positivos de antivirus en Windows).
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent  # backend/

hidden = (
    collect_submodules("app")
    + collect_submodules("psycopg")
    + collect_submodules("uvicorn")
    + [
        # Implementación binaria de psycopg: en Windows no hay libpq del sistema de respaldo.
        "psycopg_binary",
        "psycopg_binary.pq",
        "psycopg_binary._psycopg",
        "email_validator",  # EmailStr de pydantic
        "_cffi_backend",  # argon2-cffi
        "sqlalchemy.dialects.postgresql.psycopg",
    ]
)

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "migrations"), "migrations")],
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "mypy", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="contador-backend",
    console=True,  # Tauri lo lanza oculto; la consola sirve para leer el log
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="contador-backend", upx=False)
