"""Lectura de la version del proyecto."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_dir() -> Path:
    """Directorio donde estan VERSION y los recursos empaquetados."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def project_dir() -> Path:
    """Directorio de la aplicacion cuando corre desde el codigo fuente."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_version() -> str:
    version_file = resource_dir() / "VERSION"
    if not version_file.is_file():
        version_file = project_dir() / "VERSION"
    return version_file.read_text(encoding="utf-8").strip()
