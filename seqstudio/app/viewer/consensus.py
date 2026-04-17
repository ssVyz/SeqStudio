"""Consensus sequence: pinned row rendered below the alignment (but above the
conservation track). Computed once per alignment open; rules are configurable.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from seqstudio.app.models.sequence_document import SequenceDocument
from seqstudio.app.viewer.view_state import ViewState


CONSENSUS_HEIGHT = 24


IUPAC = {
    frozenset("A"): "A",
    frozenset("C"): "C",
    frozenset("G"): "G",
    frozenset("T"): "T",
    frozenset("U"): "U",
    frozenset("AG"): "R",
    frozenset("CT"): "Y",
    frozenset("CU"): "Y",
    frozenset("GT"): "K",
    frozenset("GU"): "K",
    frozenset("AC"): "M",
    frozenset("GC"): "S",
    frozenset("AT"): "W",
    frozenset("AU"): "W",
    frozenset("CGT"): "B",
    frozenset("AGT"): "D",
    frozenset("ACT"): "H",
    frozenset("ACG"): "V",
    frozenset("ACGT"): "N",
    frozenset("ACGU"): "N",
}


@dataclass
class ConsensusConfig:
    majority_threshold: float = 0.6   # IUPAC below this
    gap_threshold: float = 0.5        # gaps above this → '-'
    use_iupac: bool = True


class ConsensusWorker(QObject):
    result = Signal(str)

    def __init__(self, document: SequenceDocument, config: ConsensusConfig):
        super().__init__()
        self._doc = document
        self._config = config

    def run(self) -> None:
        doc = self._doc
        if not doc.is_aligned or doc.alignment_length is None:
            self.result.emit("")
            return
        n_cols = doc.alignment_length
        n_rows = len(doc)
        seqs = [doc.sequence(r) for r in range(n_rows)]
        out = []
        for col in range(n_cols):
            counts: dict[str, int] = {}
            gaps = 0
            for seq in seqs:
                if col >= len(seq):
                    gaps += 1
                    continue
                ch = seq[col].upper()
                if ch in ("-", "."):
                    gaps += 1
                    continue
                counts[ch] = counts.get(ch, 0) + 1
            total = n_rows
            if total > 0 and gaps / total >= self._config.gap_threshold:
                out.append("-")
                continue
            if not counts:
                out.append("-")
                continue
            top_ch, top_n = max(counts.items(), key=lambda kv: kv[1])
            denom = sum(counts.values())
            if top_n / denom >= self._config.majority_threshold or not self._config.use_iupac:
                out.append(top_ch)
                continue
            key = frozenset(counts.keys())
            out.append(IUPAC.get(key, "N"))
        self.result.emit("".join(out))


class ConsensusTrack(QWidget):
    """Pinned row displaying the consensus sequence below the alignment."""

    def __init__(self, document: SequenceDocument, state: ViewState, parent=None):
        super().__init__(parent)
        self._doc = document
        self._state = state
        self._consensus: str = ""
        self._config = ConsensusConfig()
        self.setFixedHeight(CONSENSUS_HEIGHT)
        self.setAutoFillBackground(True)
        self._thread: QThread | None = None
        self._worker: ConsensusWorker | None = None

        state.viewport_changed.connect(self.update)
        state.zoom_changed.connect(self.update)
        state.colour_changed.connect(self.update)

    def config(self) -> ConsensusConfig:
        return self._config

    def set_config(self, cfg: ConsensusConfig) -> None:
        self._config = cfg
        self.recompute()

    def consensus(self) -> str:
        return self._consensus

    def recompute(self) -> None:
        self._cancel()
        self._thread = QThread()
        self._worker = ConsensusWorker(self._doc, self._config)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.result.connect(self._on_result)
        self._worker.result.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _cancel(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(100)
        self._thread = None
        self._worker = None

    def _on_result(self, s: str) -> None:
        self._consensus = s
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#eef2f7"))
        p.setPen(QPen(QColor("#b0b8c4")))
        p.drawLine(0, 0, self.width(), 0)

        cw = self._state.cell_width
        h_off = self._state.h_offset
        scheme = self._state.scheme

        font = QFont("Courier New")
        font.setStyleHint(QFont.TypeWriter)
        font.setPointSize(10)
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)
        show_letters = self._state.show_letters()

        if not self._consensus:
            p.setPen(QPen(QColor("#777")))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Consensus: (not computed — open an aligned file)")
            p.end()
            return

        first_col = max(0, h_off // cw)
        last_col = min(len(self._consensus), (h_off + self.width()) // cw + 1)

        ch_height = self.height()
        for col in range(first_col, last_col):
            ch_ = self._consensus[col]
            x = col * cw - h_off
            bg = scheme.background_for(ch_)
            p.fillRect(x, 1, cw, ch_height - 2, bg)
            if show_letters:
                p.setPen(QPen(scheme.text))
                tw = fm.horizontalAdvance(ch_)
                p.drawText(x + (cw - tw) // 2,
                           (ch_height + fm.ascent() - fm.descent()) // 2, ch_)
        p.end()
