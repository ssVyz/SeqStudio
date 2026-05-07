"""Left-panel file browser — tree of the open folder, filtered to sequence files."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QFileInfo, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from seqstudio.app.io.format_detector import FASTA_EXTS, TEXT_EXTS, is_sequence_file
from seqstudio.app.io.sam_align import create_alignment_from_sam
from seqstudio.app.sam_align_dialog import SamAlignDialog


class SequenceFilterProxy(QSortFilterProxyModel):
    """Show directories and sequence files; hide everything else (unless toggled)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.show_all = False

    def set_show_all(self, show: bool) -> None:
        self.show_all = show
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        info: QFileInfo = model.fileInfo(index)
        if info.isDir():
            name = info.fileName()
            return name not in (".", "..") and not name.startswith(".")
        if self.show_all:
            return not info.fileName().startswith(".") and info.suffix() != "ssidx"
        p = Path(info.filePath())
        if p.suffix.lower() == ".sam":
            return True
        if p.suffix.lower() in TEXT_EXTS:
            return True
        return is_sequence_file(p)


class FileBrowser(QWidget):
    file_opened = Signal(str)
    file_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root: Path | None = None

        self._model = QFileSystemModel()
        self._model.setRootPath("")
        self._model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)

        self._proxy = SequenceFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self.tree = QTreeView()
        self.tree.setModel(self._proxy)
        self.tree.setHeaderHidden(False)
        self.tree.setSelectionMode(QTreeView.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.doubleClicked.connect(self._on_double_click)
        self.tree.clicked.connect(self._on_click)

        # Hide size/type/date columns by default — too cluttered for narrow panel.
        for col in (1, 2, 3):
            self.tree.setColumnHidden(col, True)

        header = QHBoxLayout()
        header.setContentsMargins(6, 4, 4, 4)
        self._path_label = QLabel("(no folder open)")
        self._path_label.setStyleSheet("color: #555; font-size: 11px;")
        header.addWidget(self._path_label, 1)

        self._toggle_all = QToolButton()
        self._toggle_all.setText("All files")
        self._toggle_all.setCheckable(True)
        self._toggle_all.setToolTip("Show all files (not just sequence files)")
        self._toggle_all.toggled.connect(self._proxy.set_show_all)
        header.addWidget(self._toggle_all)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addWidget(self.tree, 1)

    def set_root(self, path: Path) -> None:
        self._root = Path(path)
        src_index = self._model.setRootPath(str(path))
        self.tree.setRootIndex(self._proxy.mapFromSource(src_index))
        self._path_label.setText(str(path))

    def _index_path(self, proxy_index) -> Path:
        src = self._proxy.mapToSource(proxy_index)
        return Path(self._model.filePath(src))

    def _on_double_click(self, index) -> None:
        path = self._index_path(index)
        if path.is_file():
            self.file_opened.emit(str(path))

    def _on_click(self, index) -> None:
        path = self._index_path(index)
        if path.is_file():
            self.file_selected.emit(str(path))

    def current_selected_files(self) -> list[Path]:
        out = []
        for idx in self.tree.selectionModel().selectedRows():
            p = self._index_path(idx)
            if p.is_file():
                out.append(p)
        return out

    def _on_context_menu(self, pos) -> None:
        index = self.tree.indexAt(pos)
        if not index.isValid():
            return
        path = self._index_path(index)
        menu = QMenu(self)

        selected = self.current_selected_files()
        fasta_selected = [p for p in selected if p.suffix.lower() in FASTA_EXTS]
        sam_selected = [p for p in selected if p.suffix.lower() == ".sam"]

        if len(fasta_selected) >= 2:
            act_combine = QAction(
                f"Combine {len(fasta_selected)} files to new FASTA...", self
            )
            act_combine.triggered.connect(
                lambda: self._combine_to_new_fasta(fasta_selected)
            )
            menu.addAction(act_combine)
            menu.addSeparator()

        if len(fasta_selected) == 1 and len(sam_selected) <= 1:
            fasta_one = fasta_selected[0]
            sam_one = sam_selected[0] if sam_selected else None
            act_align = QAction("Create alignment from SAM file...", self)
            act_align.triggered.connect(
                lambda: self._create_alignment_from_sam(fasta_one, sam_one)
            )
            menu.addAction(act_align)
            menu.addSeparator()

        if path.is_file():
            act_open = QAction("Open", self)
            act_open.triggered.connect(lambda: self.file_opened.emit(str(path)))
            menu.addAction(act_open)

        act_reveal = QAction("Reveal in file manager", self)
        act_reveal.triggered.connect(lambda: _reveal(path))
        menu.addAction(act_reveal)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _create_alignment_from_sam(
        self, fasta_path: Path, sam_path: Path | None
    ) -> None:
        dlg = SamAlignDialog(fasta_path=fasta_path, sam_path=sam_path, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        fasta, sam, out = dlg.values()

        if not str(fasta).strip() or not fasta.is_file():
            QMessageBox.warning(
                self, "Create alignment from SAM",
                f"Query FASTA not found:\n{fasta}",
            )
            return
        if not str(sam).strip() or not sam.is_file():
            QMessageBox.warning(
                self, "Create alignment from SAM",
                f"SAM file not found:\n{sam}",
            )
            return
        if not str(out).strip():
            QMessageBox.warning(
                self, "Create alignment from SAM",
                "Please choose an output FASTA path.",
            )
            return
        if out.exists():
            resp = QMessageBox.question(
                self, "Create alignment from SAM",
                f"Output file already exists:\n{out}\n\nOverwrite?",
            )
            if resp != QMessageBox.Yes:
                return

        try:
            result = create_alignment_from_sam(fasta, sam, out)
        except ValueError as exc:
            QMessageBox.warning(self, "Create alignment from SAM", str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(
                self, "Create alignment from SAM",
                f"Could not write output:\n{exc}",
            )
            return

        msg = (
            f"Wrote aligned FASTA: {result.aligned_count} sequences "
            f"× {result.total_columns} columns\n{result.output_path}"
        )
        if result.unmapped_names:
            n = len(result.unmapped_names)
            sample = ", ".join(result.unmapped_names[:5])
            more = f" and {n - 5} more" if n > 5 else ""
            msg += f"\n\n{n} unmapped sequence(s) excluded: {sample}{more}"
        QMessageBox.information(self, "Create alignment from SAM", msg)

    def _combine_to_new_fasta(self, files: list[Path]) -> None:
        if len(files) < 2:
            return
        suggested = files[0].with_name("combined.fasta")
        path, _ = QFileDialog.getSaveFileName(
            self, "Combine selected files as FASTA",
            str(suggested),
            "FASTA (*.fasta *.fa *.afa *.fas);;All files (*)",
        )
        if not path:
            return
        out = Path(path)
        if out.suffix == "":
            out = out.with_suffix(".fasta")

        try:
            with out.open("w", encoding="utf-8") as fout:
                for src in files:
                    ended_with_newline = True
                    with src.open("r", encoding="utf-8", errors="replace") as fin:
                        for line in fin:
                            fout.write(line)
                            ended_with_newline = line.endswith("\n")
                    if not ended_with_newline:
                        fout.write("\n")
        except OSError as exc:
            QMessageBox.warning(
                self, "Combine to new FASTA",
                f"Could not write {out}:\n{exc}",
            )


def _reveal(path: Path) -> None:
    import subprocess
    import sys
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])
