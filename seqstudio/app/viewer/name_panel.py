"""Sequence name sidebar — vertical-scroll synchronized, horizontally fixed."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from seqstudio.app.models.sequence_document import SequenceDocument
from seqstudio.app.viewer.view_state import Selection, ViewState


class NamePanel(QWidget):
    row_clicked = Signal(int, bool)  # row, shift_held

    def __init__(self, document: SequenceDocument, state: ViewState, parent=None):
        super().__init__(parent)
        self._doc = document
        self._state = state
        self.setMinimumWidth(140)
        self.setAutoFillBackground(True)
        self._font = QFont()
        self._font.setPointSize(9)
        state.viewport_changed.connect(self.update)
        state.zoom_changed.connect(self.update)
        state.selection_changed.connect(self.update)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#f7f7f9"))

        ch = self._state.cell_height
        v = self._state.v_offset
        first = v // ch
        last = (v + self.height()) // ch + 1
        last = min(last, len(self._doc))

        fm = QFontMetrics(self._font)
        p.setFont(self._font)

        sel = self._state.selection

        for row in range(first, last):
            y = row * ch - v
            if sel is not None and sel.row_start <= row < sel.row_end:
                p.fillRect(0, y, self.width(), ch, QColor(220, 230, 245))
            else:
                if row % 2 == 0:
                    p.fillRect(0, y, self.width(), ch, QColor("#ffffff"))
                else:
                    p.fillRect(0, y, self.width(), ch, QColor("#f3f3f5"))

            name = self._doc.rows[row].id
            text = fm.elidedText(name, Qt.ElideRight, self.width() - 10)
            p.setPen(QPen(QColor("#222")))
            p.drawText(6, y + (ch + fm.ascent() - fm.descent()) // 2, text)

        # Right border
        p.setPen(QPen(QColor("#d0d0d4")))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        p.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        y = event.position().y() + self._state.v_offset
        row = int(y // self._state.cell_height)
        if 0 <= row < len(self._doc):
            shift = bool(event.modifiers() & Qt.ShiftModifier)
            if shift and self._state.selection is not None:
                sel = self._state.selection
                r0 = min(sel.row_start, row)
                r1 = max(sel.row_end - 1, row) + 1
                self._state.set_selection(Selection(r0, r1, sel.col_start, sel.col_end))
            else:
                self._state.set_selection(
                    Selection(row, row + 1, 0, self._doc.display_length)
                )
            self.row_clicked.emit(row, shift)
