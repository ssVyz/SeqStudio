"""Read-only text viewer for plain-text files (.txt).

Loads the file straight from disk without any index or sidecar; uses
QPlainTextEdit set read-only so selection / copy / Ctrl+A / Ctrl+C all
work via the built-in handlers.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget


class TextView(QWidget):
    status_message = Signal(str)

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = Path(path)

        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setUndoRedoEnabled(False)

        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(10)
        self.editor.setFont(font)

        text = self.path.read_text(encoding="utf-8", errors="replace")
        self.editor.setPlainText(text)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.editor)
