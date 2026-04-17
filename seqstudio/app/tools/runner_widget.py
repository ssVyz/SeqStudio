"""Tool Runner UI — assembles a command string and hands it off to a terminal.

SeqStudio does not run the tool itself or monitor the process. The user runs
the tool in the terminal, the tool writes output files to the open folder,
and the user opens the results manually via the file browser.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from seqstudio.app.tools.tool_definition import CURATED_TOOLS, ToolDefinition
from seqstudio.app.tools.tool_discovery import ToolStatus, fetch_help_text, scan_tools
from seqstudio.app.tools.tool_runner import open_in_terminal


FREEFORM_LABEL = "freeform / other"


class _HelpFetchThread(QThread):
    ready = Signal(str)

    def __init__(self, binary: str):
        super().__init__()
        self._binary = binary

    def run(self) -> None:
        text = fetch_help_text(self._binary)
        self.ready.emit(text)


class ToolRunnerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cwd: Path = Path.cwd()
        self._statuses: list[ToolStatus] = scan_tools()
        self._current_tool: ToolDefinition | None = None
        self._help_thread: _HelpFetchThread | None = None

        self._build_ui()
        self._populate_tools()
        self._rebuild_command()

    # --- UI construction -----------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(6)

        # Tool selector row
        row = QHBoxLayout()
        row.addWidget(QLabel("Tool:"))
        self.tool_combo = QComboBox()
        self.tool_combo.currentIndexChanged.connect(self._on_tool_changed)
        row.addWidget(self.tool_combo, 1)
        self.install_label = QLabel()
        self.install_label.setOpenExternalLinks(True)
        self.install_label.setTextFormat(Qt.RichText)
        row.addWidget(self.install_label)
        outer.addLayout(row)

        # Freeform binary row (only shown in freeform mode)
        self.binary_row = QHBoxLayout()
        self.binary_row.addWidget(QLabel("Binary / command:"))
        self.binary_edit = QLineEdit()
        self.binary_edit.textChanged.connect(self._rebuild_command)
        self.binary_row.addWidget(self.binary_edit, 1)
        self.binary_container = QWidget()
        self.binary_container.setLayout(self.binary_row)
        outer.addWidget(self.binary_container)
        self.binary_container.setVisible(False)

        # Input files
        row_in = QHBoxLayout()
        row_in.addWidget(QLabel("Input files:"))
        self.input_edit = QLineEdit()
        self.input_edit.textChanged.connect(self._rebuild_command)
        row_in.addWidget(self.input_edit, 1)
        btn_browse_in = QPushButton("Browse...")
        btn_browse_in.clicked.connect(self._browse_input)
        row_in.addWidget(btn_browse_in)
        outer.addLayout(row_in)

        # Output
        row_out = QHBoxLayout()
        row_out.addWidget(QLabel("Output:"))
        self.output_edit = QLineEdit()
        self.output_edit.textChanged.connect(self._rebuild_command)
        row_out.addWidget(self.output_edit, 1)
        btn_browse_out = QPushButton("Browse...")
        btn_browse_out.clicked.connect(self._browse_output)
        row_out.addWidget(btn_browse_out)
        outer.addLayout(row_out)

        # Arguments
        outer.addWidget(QLabel("Arguments (appended verbatim):"))
        self.args_edit = QLineEdit()
        self.args_edit.textChanged.connect(self._rebuild_command)
        outer.addWidget(self.args_edit)

        # Splitter: command preview + help text
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        preview_box = QWidget()
        pv = QVBoxLayout(preview_box)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(QLabel("Full command preview:"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        mono = QFont("Courier New")
        mono.setStyleHint(QFont.TypeWriter)
        self.preview.setFont(mono)
        self.preview.setFixedHeight(60)
        pv.addWidget(self.preview)

        btn_row = QHBoxLayout()
        btn_copy = QPushButton("Copy command")
        btn_copy.clicked.connect(self._copy_command)
        btn_run = QPushButton("Open in external terminal →")
        btn_run.clicked.connect(self._open_terminal)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_run)
        pv.addLayout(btn_row)
        splitter.addWidget(preview_box)

        help_box = QWidget()
        hv = QVBoxLayout(help_box)
        hv.setContentsMargins(0, 0, 0, 0)
        self.help_label = QLabel("Help text:")
        hv.addWidget(self.help_label)
        self.help_view = QPlainTextEdit()
        self.help_view.setReadOnly(True)
        self.help_view.setFont(mono)
        hv.addWidget(self.help_view, 1)
        splitter.addWidget(help_box)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        outer.addWidget(splitter, 1)

    def _populate_tools(self) -> None:
        self.tool_combo.blockSignals(True)
        self.tool_combo.clear()
        for status in self._statuses:
            label = f"{status.definition.name}  ({status.definition.binary})"
            if not status.installed:
                label += "  — not installed"
            self.tool_combo.addItem(label, status)
            idx = self.tool_combo.count() - 1
            if not status.installed:
                self.tool_combo.setItemData(
                    idx,
                    f"Install: {status.definition.install_url}",
                    Qt.ToolTipRole,
                )
        self.tool_combo.addItem(FREEFORM_LABEL, None)
        self.tool_combo.blockSignals(False)
        self._on_tool_changed(self.tool_combo.currentIndex())

    # --- external API --------------------------------------------------

    def set_cwd(self, path: Path) -> None:
        self._cwd = Path(path)
        self._rebuild_command()

    def set_input_files(self, paths: list[Path]) -> None:
        text = " ".join(_quote_if_needed(str(p)) for p in paths)
        self.input_edit.setText(text)
        self._auto_output()

    def add_input_file(self, path: Path) -> None:
        existing = self.input_edit.text().strip()
        chunk = _quote_if_needed(str(path))
        self.input_edit.setText(f"{existing} {chunk}".strip() if existing else chunk)
        self._auto_output()

    def statuses(self) -> list[ToolStatus]:
        return self._statuses

    # --- signal handlers ----------------------------------------------

    def _on_tool_changed(self, idx: int) -> None:
        data = self.tool_combo.itemData(idx)
        if data is None:
            self._current_tool = None
            self.binary_container.setVisible(True)
            self.install_label.clear()
            self.help_view.clear()
            self.args_edit.setText("")
        else:
            status: ToolStatus = data
            self._current_tool = status.definition
            self.binary_container.setVisible(False)
            if not status.installed:
                url = status.definition.install_url
                self.install_label.setText(
                    f'<a href="{url}">not installed — how to get it</a>'
                )
            else:
                self.install_label.setText(f"<span style='color:#388e3c'>installed: {status.path}</span>")
            self.args_edit.setText(status.definition.defaults)
            self._launch_help_fetch(status.definition.binary)
        self._auto_output()
        self._rebuild_command()

    def _launch_help_fetch(self, binary: str) -> None:
        self.help_view.setPlainText("Fetching --help ...")
        if self._help_thread is not None and self._help_thread.isRunning():
            self._help_thread.quit()
            self._help_thread.wait(100)
        self._help_thread = _HelpFetchThread(binary)
        self._help_thread.ready.connect(self._on_help_ready)
        self._help_thread.start()

    def _on_help_ready(self, text: str) -> None:
        self.help_view.setPlainText(text or "(no help output)")

    def _auto_output(self) -> None:
        if self._current_tool is None:
            return
        inputs = _split_paths(self.input_edit.text())
        if not inputs:
            return
        first = Path(inputs[0])
        suggested = first.with_name(first.stem + self._current_tool.output_suffix)
        self.output_edit.setText(str(suggested))

    def _browse_input(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Select input file(s)", str(self._cwd))
        if paths:
            current = self.input_edit.text().strip()
            chunks = [_quote_if_needed(p) for p in paths]
            joined = " ".join(chunks)
            self.input_edit.setText(f"{current} {joined}".strip() if current else joined)
            self._auto_output()

    def _browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Select output file", str(self._cwd))
        if path:
            self.output_edit.setText(path)

    def _copy_command(self) -> None:
        QApplication.clipboard().setText(self.preview.toPlainText())

    def _open_terminal(self) -> None:
        cmd = self.preview.toPlainText().strip()
        if not cmd:
            QMessageBox.information(self, "Tool Runner", "No command to run.")
            return
        try:
            open_in_terminal(cmd, self._cwd)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Tool Runner", f"Failed to open terminal:\n{exc}")

    # --- command assembly ---------------------------------------------

    def _rebuild_command(self) -> None:
        parts = _assemble_command(
            tool=self._current_tool,
            freeform_binary=self.binary_edit.text().strip(),
            input_text=self.input_edit.text().strip(),
            output_text=self.output_edit.text().strip(),
            args=self.args_edit.text().strip(),
        )
        self.preview.setPlainText(parts)


def _assemble_command(tool: ToolDefinition | None,
                      freeform_binary: str,
                      input_text: str,
                      output_text: str,
                      args: str) -> str:
    if tool is None:
        binary = freeform_binary
        if not binary:
            return ""
        segs = [binary]
        if input_text:
            segs.append(input_text)
        if output_text:
            segs.append(f"> {_quote_if_needed(output_text)}")
        if args:
            segs.append(args)
        return " ".join(segs).strip()

    segs: list[str] = [tool.binary]
    if input_text:
        inputs = _split_paths(input_text)
        if tool.input_flag == "":
            segs.append(" ".join(_quote_if_needed(p) for p in inputs))
        else:
            if tool.multi_input:
                for p in inputs:
                    segs.append(f"{tool.input_flag} {_quote_if_needed(p)}")
            else:
                segs.append(f"{tool.input_flag} {_quote_if_needed(inputs[0])}")
                for p in inputs[1:]:
                    segs.append(_quote_if_needed(p))
    if output_text:
        if tool.output_flag == ">":
            segs.append(f"> {_quote_if_needed(output_text)}")
        elif tool.output_flag == "":
            pass
        else:
            segs.append(f"{tool.output_flag} {_quote_if_needed(output_text)}")
    if args:
        segs.append(args)
    return " ".join(segs).strip()


def _quote_if_needed(path: str) -> str:
    if not path:
        return ""
    if " " in path or "\t" in path:
        return f'"{path}"'
    return path


def _split_paths(text: str) -> list[str]:
    if not text:
        return []
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        return text.split()
