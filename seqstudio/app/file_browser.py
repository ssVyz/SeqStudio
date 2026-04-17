"""Left-panel file browser — tree of the open folder, filtered to sequence files."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QFileInfo, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from seqstudio.app.io.format_detector import is_sequence_file


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
        return is_sequence_file(Path(info.filePath()))


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
        self.tree.setSelectionMode(QTreeView.SingleSelection)
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

        if path.is_file():
            act_open = QAction("Open", self)
            act_open.triggered.connect(lambda: self.file_opened.emit(str(path)))
            menu.addAction(act_open)

        act_reveal = QAction("Reveal in file manager", self)
        act_reveal.triggered.connect(lambda: _reveal(path))
        menu.addAction(act_reveal)

        menu.exec(self.tree.viewport().mapToGlobal(pos))


def _reveal(path: Path) -> None:
    import subprocess
    import sys
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])
