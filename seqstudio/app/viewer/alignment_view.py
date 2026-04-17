"""AlignmentView: composite widget hosting canvas + synchronized panels.

Owns the QScrollBars and wires them to the shared ViewState. The canvas
itself never moves in screen space — only its logical offsets change, so
repainting stays O(visible cells).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollBar, QWidget

from seqstudio.app.models.sequence_document import SequenceDocument
from seqstudio.app.viewer.canvas import AlignmentCanvas
from seqstudio.app.viewer.consensus import ConsensusTrack
from seqstudio.app.viewer.conservation import ConservationTrack
from seqstudio.app.viewer.minimap import MinimapWidget
from seqstudio.app.viewer.name_panel import NamePanel
from seqstudio.app.viewer.ruler import RulerWidget
from seqstudio.app.viewer.view_state import Selection, ViewState


class AlignmentView(QWidget):
    status_message = Signal(str)

    def __init__(self, document: SequenceDocument, parent=None):
        super().__init__(parent)
        self.document = document
        self.state = ViewState()

        self.conservation = ConservationTrack(document, self.state)
        self.consensus = ConsensusTrack(document, self.state)
        self.canvas = AlignmentCanvas(document, self.state, conservation=self.conservation)
        self.ruler = RulerWidget(document.display_length, self.state)
        self.name_panel = NamePanel(document, self.state)
        self.minimap = MinimapWidget(document, self.state)

        self.h_scroll = QScrollBar(Qt.Horizontal)
        self.v_scroll = QScrollBar(Qt.Vertical)

        self._build_layout()
        self._wire_scrollbars()
        self._wire_interactions()

        self._update_scroll_ranges()
        self.state.zoom_changed.connect(self._update_scroll_ranges)

        # Kick off background computations for aligned docs.
        if document.is_aligned:
            self.conservation.recompute()
            self.consensus.recompute()

        self.canvas.hovered_cell_changed.connect(self._on_hover)
        self.state.selection_changed.connect(self._on_selection)

    # --- layout ---------------------------------------------------------

    def _build_layout(self) -> None:
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        corner = QWidget()
        corner.setAutoFillBackground(True)
        pal = corner.palette()
        pal.setColor(QPalette.Window, QColor("#f0f0f3"))
        corner.setPalette(pal)
        corner.setFixedSize(self.name_panel.minimumWidth(), self.ruler.height())

        grid.addWidget(corner,             0, 0)
        grid.addWidget(self.ruler,         0, 1)
        grid.addWidget(self.name_panel,    1, 0)
        grid.addWidget(self.canvas,        1, 1)
        grid.addWidget(self.v_scroll,      1, 2, 4, 1)

        consensus_label = _pinned_label("consensus")
        conservation_label = _pinned_label("conservation")
        minimap_label = _pinned_label("overview")
        consensus_label.setFixedWidth(self.name_panel.minimumWidth())
        conservation_label.setFixedWidth(self.name_panel.minimumWidth())
        minimap_label.setFixedWidth(self.name_panel.minimumWidth())

        grid.addWidget(consensus_label,      2, 0)
        grid.addWidget(self.consensus,       2, 1)
        grid.addWidget(conservation_label,   3, 0)
        grid.addWidget(self.conservation,    3, 1)
        grid.addWidget(minimap_label,        4, 0)
        grid.addWidget(self.minimap,         4, 1)
        grid.addWidget(self.h_scroll,        5, 1)

        grid.setRowStretch(1, 1)
        grid.setColumnStretch(1, 1)

    # --- scroll bars ----------------------------------------------------

    def _wire_scrollbars(self) -> None:
        self.h_scroll.valueChanged.connect(
            lambda v: self.state.set_offsets(v, self.state.v_offset)
        )
        self.v_scroll.valueChanged.connect(
            lambda v: self.state.set_offsets(self.state.h_offset, v)
        )

    def _update_scroll_ranges(self) -> None:
        cw = self.state.cell_width
        ch = self.state.cell_height
        content_w = self.document.display_length * cw
        content_h = len(self.document) * ch

        page_w = max(1, self.canvas.width())
        page_h = max(1, self.canvas.height())

        self.h_scroll.setRange(0, max(0, content_w - page_w))
        self.h_scroll.setPageStep(page_w)
        self.h_scroll.setSingleStep(cw)

        self.v_scroll.setRange(0, max(0, content_h - page_h))
        self.v_scroll.setPageStep(page_h)
        self.v_scroll.setSingleStep(ch)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scroll_ranges()

    # --- interactions ---------------------------------------------------

    def _wire_interactions(self) -> None:
        self.ruler.column_clicked.connect(self._on_column_selected)
        self.minimap.jump_to_column.connect(self.go_to_column)

    def go_to_column(self, col: int) -> None:
        target_x = col * self.state.cell_width - self.canvas.width() // 2
        self.h_scroll.setValue(max(0, target_x))

    def go_to_row(self, row: int) -> None:
        target_y = row * self.state.cell_height - self.canvas.height() // 2
        self.v_scroll.setValue(max(0, target_y))

    def _on_column_selected(self, col: int) -> None:
        self.state.set_selection(
            Selection(0, len(self.document), col, col + 1)
        )

    # --- status bar hooks ----------------------------------------------

    def _on_hover(self, row: int, col: int) -> None:
        if row < 0 or col < 0:
            self.status_message.emit("")
            return
        aln_1based = col + 1
        seq_row = self.document.rows[row]
        mapper = self.document.mapper(row)
        seq_idx = mapper.alignment_to_sequence(col)
        seq_pos = "gap" if seq_idx is None else str(seq_idx + 1)
        ch = self.document.slice(row, col, col + 1)
        self.status_message.emit(
            f"{seq_row.id}  col {aln_1based} / seq pos {seq_pos}  ({ch or '-'})"
        )

    def _on_selection(self) -> None:
        sel = self.state.selection
        if sel is None or sel.is_empty():
            return
        c0 = sel.col_start + 1
        c1 = sel.col_end
        n_rows = sel.row_end - sel.row_start
        self.status_message.emit(
            f"Selection: {n_rows} rows × cols {c0}–{c1} (alignment, 1-based)"
        )

    # --- search ---------------------------------------------------------

    def search(self, motif: str) -> int:
        motif = motif.strip().upper()
        if not motif:
            self.state.clear_search()
            return 0
        matches: dict[int, list[tuple[int, int]]] = {}
        count = 0
        for row in range(len(self.document)):
            seq = self.document.sequence(row).upper()
            spans: list[tuple[int, int]] = []
            start = 0
            while True:
                idx = seq.find(motif, start)
                if idx < 0:
                    break
                spans.append((idx, idx + len(motif)))
                start = idx + 1
                count += 1
            if spans:
                matches[row] = spans
        self.state.set_search_matches(matches)
        return count

    # --- export ---------------------------------------------------------

    def export_consensus(self, path) -> None:
        from pathlib import Path
        consensus = self.consensus.consensus()
        if not consensus:
            return
        p = Path(path)
        header = f">{self.document.source_path.stem}_consensus"
        p.write_text(f"{header}\n{consensus}\n", encoding="utf-8")


def _pinned_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "QLabel { color: #555; background: #f0f0f3; padding-left: 6px; "
        "border-right: 1px solid #d0d0d4; font-size: 10px; }"
    )
    lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    return lbl
