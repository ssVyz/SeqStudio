"""Shared viewer state: zoom, scroll offsets, selection, colour scheme."""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from seqstudio.app.viewer.colors import STANDARD_NUCLEOTIDE, ColorScheme


@dataclass
class Selection:
    row_start: int
    row_end: int   # exclusive
    col_start: int
    col_end: int   # exclusive

    def is_empty(self) -> bool:
        return self.row_end <= self.row_start or self.col_end <= self.col_start


class ViewState(QObject):
    """Holds the viewer's scroll/zoom/selection state and emits signals on change."""

    viewport_changed = Signal()
    zoom_changed = Signal()
    selection_changed = Signal()
    colour_changed = Signal()
    highlight_changed = Signal()

    MIN_CELL_WIDTH = 2
    MAX_CELL_WIDTH = 40

    def __init__(self) -> None:
        super().__init__()
        self.cell_width: int = 14
        self.cell_height: int = 18
        self.h_offset: int = 0   # pixels
        self.v_offset: int = 0   # pixels
        self.scheme: ColorScheme = STANDARD_NUCLEOTIDE
        self.selection: Selection | None = None
        self.show_conservation_bg: bool = False
        self.coord_mode: str = "alignment"   # or "sequence"
        self.search_matches: dict[int, list[tuple[int, int]]] = {}

    # Zoom ----------------------------------------------------------------
    def set_cell_size(self, width: int, height: int) -> None:
        w = max(self.MIN_CELL_WIDTH, min(self.MAX_CELL_WIDTH, int(width)))
        h = max(self.MIN_CELL_WIDTH + 2, min(self.MAX_CELL_WIDTH + 6, int(height)))
        if w != self.cell_width or h != self.cell_height:
            self.cell_width = w
            self.cell_height = h
            self.zoom_changed.emit()

    def zoom(self, delta: int) -> None:
        step = 1 if abs(delta) <= 2 else 2
        new_w = self.cell_width + (step if delta > 0 else -step)
        new_h = int(round(new_w * (18 / 14)))
        self.set_cell_size(new_w, new_h)

    def show_letters(self) -> bool:
        return self.cell_width >= 7 and self.cell_height >= 10

    # Scroll --------------------------------------------------------------
    def set_offsets(self, h: int, v: int) -> None:
        if h != self.h_offset or v != self.v_offset:
            self.h_offset = max(0, int(h))
            self.v_offset = max(0, int(v))
            self.viewport_changed.emit()

    # Selection -----------------------------------------------------------
    def set_selection(self, sel: Selection | None) -> None:
        self.selection = sel
        self.selection_changed.emit()

    # Colour --------------------------------------------------------------
    def set_scheme(self, scheme: ColorScheme) -> None:
        if scheme is not self.scheme:
            self.scheme = scheme
            self.colour_changed.emit()

    def set_conservation_bg(self, enabled: bool) -> None:
        if self.show_conservation_bg != enabled:
            self.show_conservation_bg = enabled
            self.highlight_changed.emit()

    def set_coord_mode(self, mode: str) -> None:
        if mode not in ("alignment", "sequence"):
            return
        if mode != self.coord_mode:
            self.coord_mode = mode
            self.highlight_changed.emit()

    # Search highlights ---------------------------------------------------
    def set_search_matches(self, matches: dict[int, list[tuple[int, int]]]) -> None:
        self.search_matches = matches
        self.highlight_changed.emit()

    def clear_search(self) -> None:
        if self.search_matches:
            self.search_matches = {}
            self.highlight_changed.emit()
