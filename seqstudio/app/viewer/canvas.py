"""AlignmentCanvas: virtualized QPainter-based residue renderer.

Only cells whose logical coordinates lie within the visible viewport are
painted. All scroll offsets are logical — the widget itself is fixed at
viewport size, matching the JetBrains/IntelliJ approach of letting an
outer layout manage scrollbars.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from seqstudio.app.models.sequence_document import SequenceDocument
from seqstudio.app.viewer.consensus import (
    is_unambiguous as _consensus_unambiguous,
    matches_consensus as _matches,
)
from seqstudio.app.viewer.view_state import Selection, ViewState


class AlignmentCanvas(QWidget):
    """Draws residue cells for a SequenceDocument within the current viewport."""

    hovered_cell_changed = Signal(int, int)   # row, col (-1, -1 when none)
    scroll_v_requested = Signal(int)          # delta in pixels (positive = scroll down)
    scroll_h_requested = Signal(int)          # delta in pixels (positive = scroll right)

    def __init__(self, document: SequenceDocument, state: ViewState,
                 conservation=None, consensus=None, parent=None):
        super().__init__(parent)
        self._doc = document
        self._state = state
        self._conservation = conservation   # ConservationTrack | None (for entropy values)
        self._consensus = consensus         # ConsensusTrack | None (for dot-matching)

        self.setAutoFillBackground(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

        self._font = QFont("Courier New")
        self._font.setStyleHint(QFont.TypeWriter)
        self._font.setPointSize(10)

        self._drag_anchor: tuple[int, int] | None = None

        state.viewport_changed.connect(self.update)
        state.zoom_changed.connect(self._on_zoom)
        state.selection_changed.connect(self.update)
        state.colour_changed.connect(self.update)
        state.highlight_changed.connect(self.update)
        if consensus is not None:
            consensus.consensus_changed.connect(self.update)

    def sizeHint(self):
        return self.size()

    # -- layout helpers ---------------------------------------------------

    def content_width(self) -> int:
        return self._doc.display_length * self._state.cell_width

    def content_height(self) -> int:
        return len(self._doc) * self._state.cell_height

    def visible_cols(self) -> tuple[int, int]:
        cw = self._state.cell_width
        first = self._state.h_offset // cw
        last = (self._state.h_offset + self.width()) // cw + 1
        return max(0, first), min(self._doc.display_length, last)

    def visible_rows(self) -> tuple[int, int]:
        ch = self._state.cell_height
        first = self._state.v_offset // ch
        last = (self._state.v_offset + self.height()) // ch + 1
        return max(0, first), min(len(self._doc), last)

    def cell_at(self, pos) -> tuple[int, int] | None:
        x = pos.x() + self._state.h_offset
        y = pos.y() + self._state.v_offset
        if x < 0 or y < 0:
            return None
        col = x // self._state.cell_width
        row = y // self._state.cell_height
        if row >= len(self._doc) or col >= self._doc.display_length:
            return None
        return int(row), int(col)

    # -- events -----------------------------------------------------------

    def _on_zoom(self) -> None:
        self._font.setPointSizeF(max(6.0, min(self._state.cell_height * 0.55, 18.0)))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#ffffff"))

        doc = self._doc
        state = self._state
        if len(doc) == 0 or doc.display_length == 0:
            p.end()
            return

        cw = state.cell_width
        ch = state.cell_height
        first_row, last_row = self.visible_rows()
        first_col, last_col = self.visible_cols()
        if last_row <= first_row or last_col <= first_col:
            p.end()
            return

        show_letters = state.show_letters()
        scheme = state.scheme

        conservation_bg = state.show_conservation_bg and self._conservation is not None
        entropy_values = self._conservation.entropy if conservation_bg else None

        consensus_str = self._consensus.consensus() if self._consensus is not None else ""
        dots_mode = state.dots_for_matching and bool(consensus_str)
        dot_bg = QColor("#dcdcdf")
        dot_pen = QPen(QColor("#555"))

        p.setFont(self._font)
        fm = QFontMetrics(self._font)
        text_pen = QPen(scheme.text)

        for row in range(first_row, last_row):
            seq = doc.slice(row, first_col, last_col)
            y_top = row * ch - state.v_offset
            for local_idx, ch_ in enumerate(seq):
                col = first_col + local_idx
                x_left = col * cw - state.h_offset
                cell_rect = QRect(x_left, y_top, cw, ch)

                is_match = (
                    dots_mode
                    and col < len(consensus_str)
                    and _consensus_unambiguous(consensus_str[col])
                    and _matches(ch_, consensus_str[col])
                )

                if is_match:
                    p.fillRect(cell_rect, dot_bg)
                elif conservation_bg and entropy_values is not None and col < len(entropy_values):
                    p.fillRect(cell_rect, _entropy_to_color(entropy_values[col]))
                else:
                    p.fillRect(cell_rect, scheme.background_for(ch_))

                if show_letters:
                    if is_match:
                        p.setPen(dot_pen)
                        glyph = "."
                    else:
                        p.setPen(text_pen)
                        glyph = ch_
                    tw = fm.horizontalAdvance(glyph)
                    tx = x_left + (cw - tw) / 2
                    ty = y_top + (ch + fm.ascent() - fm.descent()) / 2
                    p.drawText(QPointF(tx, ty), glyph)

        # Search match highlights
        if state.search_matches:
            pen = QPen(QColor(255, 180, 0, 230))
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            for row, spans in state.search_matches.items():
                if row < first_row or row >= last_row:
                    continue
                y_top = row * ch - state.v_offset
                for (s, e) in spans:
                    if e <= first_col or s >= last_col:
                        continue
                    x1 = s * cw - state.h_offset
                    x2 = e * cw - state.h_offset
                    p.drawRect(QRect(x1, y_top, x2 - x1 - 1, ch - 1))

        # Selection rectangle
        sel = state.selection
        if sel is not None and not sel.is_empty():
            x1 = sel.col_start * cw - state.h_offset
            x2 = sel.col_end * cw - state.h_offset
            y1 = sel.row_start * ch - state.v_offset
            y2 = sel.row_end * ch - state.v_offset
            overlay = QColor(70, 130, 220, 70)
            p.fillRect(QRect(x1, y1, x2 - x1, y2 - y1), overlay)
            pen = QPen(QColor(60, 110, 200))
            pen.setWidth(1)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRect(x1, y1, x2 - x1 - 1, y2 - y1 - 1))

        p.end()

    # -- mouse / keyboard -------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        rc = self.cell_at(event.position())
        if rc is None:
            return
        row, col = rc
        if event.modifiers() & Qt.ShiftModifier and self._state.selection is not None:
            old = self._state.selection
            r0 = min(old.row_start, row)
            r1 = max(old.row_end - 1, row) + 1
            c0 = min(old.col_start, col)
            c1 = max(old.col_end - 1, col) + 1
            self._state.set_selection(Selection(r0, r1, c0, c1))
        else:
            self._drag_anchor = (row, col)
            self._state.set_selection(Selection(row, row + 1, col, col + 1))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        rc = self.cell_at(event.position())
        if rc is None:
            self.hovered_cell_changed.emit(-1, -1)
            return
        self.hovered_cell_changed.emit(rc[0], rc[1])
        if self._drag_anchor is None or not (event.buttons() & Qt.LeftButton):
            return
        ar, ac = self._drag_anchor
        row, col = rc
        r0, r1 = (ar, row) if ar <= row else (row, ar)
        c0, c1 = (ac, col) if ac <= col else (col, ac)
        self._state.set_selection(Selection(r0, r1 + 1, c0, c1 + 1))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_anchor = None

    def leaveEvent(self, event: QEvent) -> None:
        self.hovered_cell_changed.emit(-1, -1)
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            self._state.zoom(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
            return

        ad = event.angleDelta()
        rows_per_notch = 3
        ch = self._state.cell_height
        cw = self._state.cell_width

        if event.modifiers() & Qt.ShiftModifier and ad.y() != 0:
            self.scroll_h_requested.emit(int(-ad.y() / 120 * cw * rows_per_notch))
            event.accept()
            return

        if ad.y() != 0:
            self.scroll_v_requested.emit(int(-ad.y() / 120 * ch * rows_per_notch))
        if ad.x() != 0:
            self.scroll_h_requested.emit(int(-ad.x() / 120 * cw * rows_per_notch))
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_C:
            self._copy_selection_as_fasta()
            event.accept()
            return
        super().keyPressEvent(event)

    def _copy_selection_as_fasta(self) -> None:
        sel = self._state.selection
        if sel is None or sel.is_empty():
            return
        lines = []
        for row in range(sel.row_start, sel.row_end):
            srow = self._doc.rows[row]
            lines.append(f">{srow.id}")
            lines.append(self._doc.slice(row, sel.col_start, sel.col_end))
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(lines))


def _entropy_to_color(entropy: float) -> QColor:
    """Map Shannon entropy (0.0 conserved → ~2.32 variable) to a blue→red gradient."""
    max_h = 2.32  # log2(5) for ACGT-
    t = max(0.0, min(1.0, entropy / max_h))
    r = int(30 + t * (220 - 30))
    g = int(80 + (1 - abs(0.5 - t) * 2) * 80)
    b = int(180 - t * (180 - 40))
    return QColor(r, g, b)
