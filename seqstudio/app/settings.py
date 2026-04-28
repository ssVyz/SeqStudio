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


def save_dots_for_matching(enabled: bool) -> None:
    settings().setValue("dots_for_matching", bool(enabled))


def stored_dots_for_matching() -> bool:
    v = settings().value("dots_for_matching")
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("1", "true", "yes")


def save_consensus_coverage(pct: float) -> None:
    settings().setValue("consensus_coverage_pct", float(pct))


def stored_consensus_coverage() -> float | None:
    v = settings().value("consensus_coverage_pct")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
