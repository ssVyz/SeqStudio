"""Position ruler: horizontal-scroll synchronized tick bar."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from seqstudio.app.viewer.view_state import Selection, ViewState


RULER_HEIGHT = 22


class RulerWidget(QWidget):
    column_clicked = Signal(int)

    def __init__(self, total_columns: int, state: ViewState, parent=None):
        super().__init__(parent)
        self._total_columns = total_columns
        self._state = state
        self.setFixedHeight(RULER_HEIGHT)
        self.setAutoFillBackground(True)
        self._font = QFont()
        self._font.setPointSize(8)
        state.viewport_changed.connect(self.update)
        state.zoom_changed.connect(self.update)

    def set_total_columns(self, n: int) -> None:
        self._total_columns = n
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#f0f0f3"))
        p.setFont(self._font)
        fm = QFontMetrics(self._font)

        cw = self._state.cell_width
        h = self._state.h_offset

        first_col = max(0, h // cw)
        last_col = min(self._total_columns, (h + self.width()) // cw + 1)

        step = _tick_step(cw)
        first_tick = (first_col // step) * step
        pen_major = QPen(QColor("#888"))
        pen_minor = QPen(QColor("#b8b8b8"))
        pen_text = QPen(QColor("#333"))

        for col in range(first_tick, last_col + step, step):
            if col > self._total_columns:
                break
            x = col * cw - h + cw // 2
            p.setPen(pen_major if col % (step * 5) == 0 else pen_minor)
            tick_len = 8 if col % (step * 5) == 0 else 4
            p.drawLine(x, self.height() - tick_len, x, self.height())
            if col % (step * 5) == 0:
                label = str(col + 1)  # 1-based display
                tw = fm.horizontalAdvance(label)
                p.setPen(pen_text)
                p.drawText(int(x - tw / 2), fm.ascent() + 2, label)

        p.setPen(QPen(QColor("#ccc")))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        col = int((event.position().x() + self._state.h_offset) // self._state.cell_width)
        col = max(0, min(self._total_columns - 1, col))
        self.column_clicked.emit(col)


def _tick_step(cell_width: int) -> int:
    if cell_width >= 14:
        return 1
    if cell_width >= 8:
        return 2
    if cell_width >= 4:
        return 5
    return 10
