"""MainWindow: JetBrains-style layout wiring the file browser, alignment
viewer (centre), and Tool Runner (bottom dock).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QToolBar,
)

from seqstudio.app.file_browser import FileBrowser
from seqstudio.app.models.sequence_document import SequenceDocument
from seqstudio.app.settings import (
    last_folder,
    save_consensus_coverage,
    save_dots_for_matching,
    save_last_folder,
    save_scheme,
    stored_consensus_coverage,
    stored_dots_for_matching,
    stored_scheme,
)
from seqstudio.app.tools.runner_widget import ToolRunnerWidget
from seqstudio.app.viewer.alignment_view import AlignmentView
from seqstudio.app.viewer.colors import SCHEMES, get_scheme, scheme_names
from seqstudio.app.viewer.display_options import DisplayOptionsDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SeqStudio")
        self.resize(1400, 900)

        self._views: dict[str, AlignmentView] = {}

        self._build_central()
        self._build_file_browser_dock()
        self._build_tool_runner_dock()
        self._build_toolbar()
        self._build_menu()
        self._build_statusbar()

        last = last_folder()
        if last and Path(last).is_dir():
            self.open_folder(last)

    # --- layout ---------------------------------------------------------

    def _build_central(self) -> None:
        self._stack = QStackedWidget()

        welcome = QLabel(
            "<div style='color:#777; font-size:14px;'>"
            "<h2>SeqStudio</h2>"
            "<p>Open a folder to start. Double-click a sequence file to view.</p>"
            "</div>"
        )
        welcome.setAlignment(Qt.AlignCenter)
        self._stack.addWidget(welcome)

        self.setCentralWidget(self._stack)

    def _build_file_browser_dock(self) -> None:
        self.browser = FileBrowser()
        self.browser.file_opened.connect(self.open_file)
        self.browser.file_selected.connect(self._on_file_selected)

        dock = QDockWidget("Files", self)
        dock.setObjectName("FileBrowserDock")
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setWidget(self.browser)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self._browser_dock = dock

    def _build_tool_runner_dock(self) -> None:
        self.runner = ToolRunnerWidget()
        dock = QDockWidget("Tool Runner", self)
        dock.setObjectName("ToolRunnerDock")
        dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        dock.setWidget(self.runner)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self._runner_dock = dock

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        self.addToolBar(tb)

        act_open_folder = QAction("Open Folder...", self)
        act_open_folder.setShortcut(QKeySequence("Ctrl+K"))
        act_open_folder.triggered.connect(self._on_open_folder)
        tb.addAction(act_open_folder)

        tb.addSeparator()

        tb.addWidget(QLabel(" Colour scheme: "))
        self.scheme_combo = QComboBox()
        for name in scheme_names():
            self.scheme_combo.addItem(name)
        saved = stored_scheme()
        if saved and saved in SCHEMES:
            self.scheme_combo.setCurrentText(saved)
        self.scheme_combo.currentTextChanged.connect(self._on_scheme_changed)
        tb.addWidget(self.scheme_combo)

        tb.addSeparator()

        act_conservation_bg = QAction("Conservation background", self)
        act_conservation_bg.setCheckable(True)
        act_conservation_bg.toggled.connect(self._on_conservation_bg_toggled)
        tb.addAction(act_conservation_bg)

        tb.addSeparator()

        tb.addWidget(QLabel(" Go to col: "))
        self.goto_edit = QLineEdit()
        self.goto_edit.setFixedWidth(80)
        self.goto_edit.returnPressed.connect(self._on_goto)
        tb.addWidget(self.goto_edit)

        tb.addWidget(QLabel(" Find: "))
        self.find_edit = QLineEdit()
        self.find_edit.setFixedWidth(180)
        self.find_edit.setPlaceholderText("subsequence motif")
        self.find_edit.returnPressed.connect(self._on_find)
        tb.addWidget(self.find_edit)

        tb.addSeparator()

        act_zoom_in = QAction("Zoom +", self)
        act_zoom_in.setShortcut(QKeySequence("Ctrl+="))
        act_zoom_in.triggered.connect(lambda: self._current_view() and self._current_view().state.zoom(1))
        tb.addAction(act_zoom_in)

        act_zoom_out = QAction("Zoom −", self)
        act_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        act_zoom_out.triggered.connect(lambda: self._current_view() and self._current_view().state.zoom(-1))
        tb.addAction(act_zoom_out)

        tb.addSeparator()

        act_calc_consensus = QAction("Calculate Consensus", self)
        act_calc_consensus.setShortcut(QKeySequence("Ctrl+Shift+K"))
        act_calc_consensus.triggered.connect(self._on_calculate_consensus)
        tb.addAction(act_calc_consensus)
        self._act_calc_consensus = act_calc_consensus

        self.coverage_spin = QDoubleSpinBox()
        self.coverage_spin.setDecimals(2)
        self.coverage_spin.setRange(0.00, 100.00)
        self.coverage_spin.setSingleStep(1.00)
        self.coverage_spin.setSuffix(" %")
        self.coverage_spin.setFixedWidth(96)
        self.coverage_spin.setToolTip(
            "Coverage threshold: smallest IUPAC ambiguity per column "
            "whose cumulative frequency reaches this percentage."
        )
        saved_pct = stored_consensus_coverage()
        self.coverage_spin.setValue(60.00 if saved_pct is None else saved_pct)
        tb.addWidget(self.coverage_spin)

    def _build_menu(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        act_open_folder = file_menu.addAction("Open Folder...")
        act_open_folder.setShortcut(QKeySequence("Ctrl+K"))
        act_open_folder.triggered.connect(self._on_open_folder)

        act_open_file = file_menu.addAction("Open File...")
        act_open_file.setShortcut(QKeySequence("Ctrl+O"))
        act_open_file.triggered.connect(self._on_open_file)

        file_menu.addSeparator()
        file_menu.addAction(self._act_calc_consensus)

        act_export = file_menu.addAction("Export Consensus as FASTA...")
        act_export.triggered.connect(self._on_export_consensus)

        file_menu.addSeparator()
        act_quit = file_menu.addAction("Quit")
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)

        settings_menu = mb.addMenu("&Settings")
        act_display_opts = settings_menu.addAction("Display options...")
        act_display_opts.triggered.connect(self._on_display_options)

        view_menu = mb.addMenu("&View")
        view_menu.addAction(self._browser_dock.toggleViewAction())
        view_menu.addAction(self._runner_dock.toggleViewAction())

        help_menu = mb.addMenu("&Help")
        act_about = help_menu.addAction("About SeqStudio")
        act_about.triggered.connect(self._on_about)

    def _build_statusbar(self) -> None:
        self._hover_label = QLabel("")
        self._tools_label = QLabel("")
        self.statusBar().addWidget(self._hover_label, 1)
        self.statusBar().addPermanentWidget(self._tools_label)
        self._refresh_tools_label()

    def _refresh_tools_label(self) -> None:
        installed = [s for s in self.runner.statuses() if s.installed]
        total = len(self.runner.statuses())
        self._tools_label.setText(f"Tools: {len(installed)}/{total} installed")

    # --- file / folder actions -----------------------------------------

    def _on_open_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Folder")
        if path:
            self.open_folder(path)

    def _on_open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Sequence File", "",
            "Sequence files (*.fasta *.fa *.fna *.ffn *.faa *.afa *.fas *.aln *.clustal *.sto *.stockholm)",
        )
        if path:
            self.open_file(path)

    def open_folder(self, path: str | Path) -> None:
        path = Path(path)
        if not path.is_dir():
            return
        self.browser.set_root(path)
        self.runner.set_cwd(path)
        save_last_folder(str(path))

    def open_file(self, path: str | Path) -> None:
        path = Path(path)
        if not path.is_file():
            return
        key = str(path.resolve())
        if key in self._views:
            self._stack.setCurrentWidget(self._views[key])
            return
        try:
            doc = SequenceDocument.open(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Open", f"Could not open {path}:\n{exc}")
            return
        view = AlignmentView(doc)
        view.status_message.connect(self._hover_label.setText)
        current_scheme = get_scheme(self.scheme_combo.currentText())
        view.state.set_scheme(current_scheme)
        view.state.set_dots_for_matching(stored_dots_for_matching())
        self._views[key] = view
        self._stack.addWidget(view)
        self._stack.setCurrentWidget(view)
        self.setWindowTitle(f"SeqStudio — {path.name}")

    def _on_file_selected(self, path: str) -> None:
        self.runner.set_input_files([Path(path)])

    def _current_view(self) -> AlignmentView | None:
        w = self._stack.currentWidget()
        return w if isinstance(w, AlignmentView) else None

    # --- toolbar actions -----------------------------------------------

    def _on_scheme_changed(self, name: str) -> None:
        save_scheme(name)
        scheme = get_scheme(name)
        for view in self._views.values():
            view.state.set_scheme(scheme)

    def _on_conservation_bg_toggled(self, checked: bool) -> None:
        view = self._current_view()
        if view is not None:
            view.state.set_conservation_bg(checked)

    def _on_goto(self) -> None:
        view = self._current_view()
        if view is None:
            return
        text = self.goto_edit.text().strip()
        if not text:
            return
        try:
            col = int(text)
        except ValueError:
            return
        view.go_to_column(max(0, col - 1))

    def _on_find(self) -> None:
        view = self._current_view()
        if view is None:
            return
        motif = self.find_edit.text().strip()
        hits = view.search(motif)
        self._hover_label.setText(f"Search '{motif}': {hits} matches")

    def _on_calculate_consensus(self) -> None:
        view = self._current_view()
        if view is None:
            QMessageBox.information(
                self, "Calculate Consensus",
                "Open a sequence file first."
            )
            return
        pct = self.coverage_spin.value()
        save_consensus_coverage(pct)
        view.calculate_consensus(coverage=pct / 100.0)

    def _on_display_options(self) -> None:
        current = stored_dots_for_matching()
        dlg = DisplayOptionsDialog(current, parent=self)
        if dlg.exec() != DisplayOptionsDialog.Accepted:
            return
        enabled = dlg.dots_for_matching()
        save_dots_for_matching(enabled)
        for view in self._views.values():
            view.state.set_dots_for_matching(enabled)

    def _on_export_consensus(self) -> None:
        view = self._current_view()
        if view is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export consensus", "", "FASTA (*.fasta *.fa)"
        )
        if path:
            view.export_consensus(path)

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "About SeqStudio",
            "<h3>SeqStudio</h3>"
            "<p>A bioinformatics-focused desktop IDE for FASTA and alignment files.</p>"
            "<p>Built with PySide6.</p>"
        )
