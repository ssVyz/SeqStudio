"""Minimap overview: a down-sampled horizontal strip of the full alignment width.

Renders once on open (or when the window resizes), cached as a QPixmap. Clicking
on the minimap jumps the horizontal scroll there.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from seqstudio.app.models.sequence_document import SequenceDocument
from seqstudio.app.viewer.view_state import ViewState


MINIMAP_HEIGHT = 28


class MinimapWidget(QWidget):
    jump_to_column = Signal(int)

    def __init__(self, document: SequenceDocument, state: ViewState, parent=None):
        super().__init__(parent)
        self._doc = document
        self._state = state
        self._pixmap: QPixmap | None = None
        self.setFixedHeight(MINIMAP_HEIGHT)
        self.setAutoFillBackground(True)
        state.viewport_changed.connect(self.update)
        state.zoom_changed.connect(self.update)
        state.colour_changed.connect(self._invalidate)

    def _invalidate(self) -> None:
        self._pixmap = None
        self.update()

    def resizeEvent(self, event) -> None:
        self._pixmap = None
        super().resizeEvent(event)

    def _build_pixmap(self) -> None:
        n_cols = self._doc.display_length
        n_rows = len(self._doc)
        if n_cols == 0 or n_rows == 0 or self.width() < 2:
            self._pixmap = QPixmap(self.width(), MINIMAP_HEIGHT - 6)
            self._pixmap.fill(QColor("#f5f5f5"))
            return

        # Downsample to self.width() pixels across and up to ~18 rows vertically.
        target_w = max(1, self.width())
        target_h = max(1, MINIMAP_HEIGHT - 6)
        sample_rows = min(n_rows, target_h)
        row_step = max(1, n_rows // sample_rows)

        img = QImage(target_w, target_h, QImage.Format_RGB32)
        img.fill(QColor("#f5f5f5"))

        scheme = self._state.scheme
        col_step = max(1, n_cols // target_w)

        for py in range(target_h):
            src_row = min(n_rows - 1, py * row_step)
            seq = self._doc.sequence(src_row)
            for px in range(target_w):
                col = min(n_cols - 1, px * col_step)
                if col < len(seq):
                    ch = seq[col]
                    if ch in ("-", "."):
                        continue
                    color = scheme.background_for(ch)
                    img.setPixelColor(px, py, color)
        pm = QPixmap.fromImage(img)
        self._pixmap = pm

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#eeeef1"))

        if self._pixmap is None:
            self._build_pixmap()
        if self._pixmap is not None:
            p.drawPixmap(0, 3, self._pixmap)

        # Draw viewport indicator
        if self._doc.display_length > 0:
            cw = self._state.cell_width
            total_px = self._doc.display_length * cw
            if total_px > 0:
                scale = self.width() / total_px
                x = int(self._state.h_offset * scale)
                w = max(2, int(self.width() * (1 / max(1, total_px / max(1, self._parent_viewport_width())))))
                p.setPen(QPen(QColor(0, 0, 0, 160)))
                p.drawRect(x, 2, w, self.height() - 5)
        p.end()

    def _parent_viewport_width(self) -> int:
        parent = self.parent()
        if parent is None:
            return self.width()
        return max(1, parent.width())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton or self._doc.display_length == 0:
            return
        frac = event.position().x() / max(1, self.width())
        col = int(frac * self._doc.display_length)
        self.jump_to_column.emit(col)
