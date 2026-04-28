"""Per-column conservation / diversity computation.

Runs on a background thread so the viewer stays responsive. Emits progress
incrementally — the conservation track can repaint as columns are completed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from seqstudio.app.models.sequence_document import SequenceDocument
from seqstudio.app.viewer.view_state import ViewState


CONSERVATION_HEIGHT = 46


@dataclass
class ConservationResult:
    entropy: list[float]
    identity: list[float]
    gap_frac: list[float]


class ConservationWorker(QObject):
    progress = Signal(int, int)          # done, total
    result = Signal(object)              # ConservationResult
    chunk_ready = Signal(int, int, object)  # start, end, partial result snapshot

    def __init__(self, document: SequenceDocument, ignore_gaps: bool = True,
                 chunk_size: int = 2048):
        super().__init__()
        self._doc = document
        self._ignore_gaps = ignore_gaps
        self._chunk = chunk_size
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        doc = self._doc
        if not doc.is_aligned or doc.alignment_length is None:
            self.result.emit(ConservationResult([], [], []))
            return

        n_cols = doc.alignment_length
        n_rows = len(doc)
        entropy = [0.0] * n_cols
        identity = [0.0] * n_cols
        gap_frac = [0.0] * n_cols

        # Pre-load all sequences — conservation needs every column anyway, and
        # FASTA is quick to stream row-by-row.
        sequences = [doc.sequence(r) for r in range(n_rows)]

        start = 0
        while start < n_cols:
            if self._cancelled:
                return
            end = min(start + self._chunk, n_cols)
            for col in range(start, end):
                counts: dict[str, int] = {}
                gaps = 0
                for seq in sequences:
                    if col >= len(seq):
                        gaps += 1
                        continue
                    ch = seq[col].upper()
                    if ch in ("-", "."):
                        gaps += 1
                        continue
                    counts[ch] = counts.get(ch, 0) + 1
                total_nongap = sum(counts.values())
                total = n_rows
                gap_frac[col] = gaps / total if total else 0.0

                if self._ignore_gaps:
                    denom = total_nongap
                else:
                    denom = total
                    counts["-"] = gaps

                if denom == 0:
                    entropy[col] = 0.0
                    identity[col] = 0.0
                    continue

                h = 0.0
                top = 0
                for v in counts.values():
                    p = v / denom
                    if p > 0:
                        h -= p * math.log2(p)
                    if v > top:
                        top = v
                entropy[col] = h
                identity[col] = top / denom

            self.progress.emit(end, n_cols)
            self.chunk_ready.emit(start, end,
                                  ConservationResult(list(entropy), list(identity), list(gap_frac)))
            start = end

        self.result.emit(ConservationResult(entropy, identity, gap_frac))


class ConservationTrack(QWidget):
    """Histogram of per-column identity/entropy below the alignment."""

    def __init__(self, document: SequenceDocument, state: ViewState, parent=None):
        super().__init__(parent)
        self._doc = document
        self._state = state
        self._metric = "identity"   # or "entropy"
        self.setFixedHeight(CONSERVATION_HEIGHT)
        self.setAutoFillBackground(True)

        self.entropy: list[float] = []
        self.identity: list[float] = []
        self.gap_frac: list[float] = []

        self._thread: QThread | None = None
        self._worker: ConservationWorker | None = None

        state.viewport_changed.connect(self.update)
        state.zoom_changed.connect(self.update)

    # --- computation lifecycle -----------------------------------------

    def recompute(self, ignore_gaps: bool = True) -> None:
        self.cancel()
        if not self._doc.is_aligned:
            self.entropy = []
            self.identity = []
            self.gap_frac = []
            self.update()
            return
        self._thread = QThread()
        self._worker = ConservationWorker(self._doc, ignore_gaps=ignore_gaps)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.chunk_ready.connect(self._on_chunk)
        self._worker.result.connect(self._on_result)
        self._worker.result.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def cancel(self) -> None:
        worker = self._worker
        thread = self._thread
        self._worker = None
        self._thread = None
        if worker is not None:
            try:
                worker.cancel()
            except RuntimeError:
                pass
        if thread is not None:
            try:
                thread.quit()
                thread.wait(100)
            except RuntimeError:
                pass

    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None

    def _on_chunk(self, start: int, end: int, snapshot: ConservationResult) -> None:
        self.entropy = snapshot.entropy
        self.identity = snapshot.identity
        self.gap_frac = snapshot.gap_frac
        self.update()

    def _on_result(self, result: ConservationResult) -> None:
        self.entropy = result.entropy
        self.identity = result.identity
        self.gap_frac = result.gap_frac
        self.update()

    # --- display -------------------------------------------------------

    def set_metric(self, metric: str) -> None:
        if metric in ("identity", "entropy"):
            self._metric = metric
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#fafafa"))

        values = self.identity if self._metric == "identity" else self.entropy
        if not values:
            p.setPen(QPen(QColor("#888")))
            f = QFont()
            f.setPointSize(8)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Conservation: (not computed — click 'Calculate Consensus')")
            p.end()
            return

        cw = self._state.cell_width
        h_off = self._state.h_offset
        first_col = max(0, h_off // cw)
        last_col = min(len(values), (h_off + self.width()) // cw + 1)

        bar_height = self.height() - 4

        if self._metric == "identity":
            for col in range(first_col, last_col):
                v = values[col]
                x = col * cw - h_off
                bh = int(v * bar_height)
                rect_y = self.height() - bh - 2
                p.fillRect(x, rect_y, max(1, cw - 1), bh, _identity_color(v))
        else:
            max_h = 2.32
            for col in range(first_col, last_col):
                v = values[col] / max_h
                v = max(0.0, min(1.0, v))
                x = col * cw - h_off
                bh = int(v * bar_height)
                rect_y = self.height() - bh - 2
                p.fillRect(x, rect_y, max(1, cw - 1), bh, _entropy_color(v))

        p.setPen(QPen(QColor("#d0d0d0")))
        p.drawLine(0, 0, self.width(), 0)
        p.end()


def _identity_color(v: float) -> QColor:
    # High identity = dark blue, low = red-ish
    t = 1.0 - max(0.0, min(1.0, v))
    r = int(30 + t * (220 - 30))
    g = int(60 + (1 - abs(0.5 - t) * 2) * 100)
    b = int(180 - t * (180 - 40))
    return QColor(r, g, b)


def _entropy_color(t: float) -> QColor:
    r = int(30 + t * (220 - 30))
    g = int(60 + (1 - abs(0.5 - t) * 2) * 100)
    b = int(180 - t * (180 - 40))
    return QColor(r, g, b)
