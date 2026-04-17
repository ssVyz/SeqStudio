"""Persistent user preferences via QSettings."""
from __future__ import annotations

from PySide6.QtCore import QSettings


def settings() -> QSettings:
    return QSettings()


def save_last_folder(path: str) -> None:
    settings().setValue("last_folder", path)


def last_folder() -> str | None:
    v = settings().value("last_folder")
    return str(v) if v else None


def save_scheme(name: str) -> None:
    settings().setValue("colour_scheme", name)


def stored_scheme() -> str | None:
    v = settings().value("colour_scheme")
    return str(v) if v else None
