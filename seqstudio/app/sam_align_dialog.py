"""Dialog for building an aligned FASTA from a query FASTA + SAM file."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class SamAlignDialog(QDialog):
    def __init__(
        self,
        fasta_path: Path | None = None,
        sam_path: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create alignment from SAM file")
        self.setModal(True)
        self.resize(640, 0)

        self._user_edited_output = False

        outer = QVBoxLayout(self)
        outer.addWidget(QLabel(
            "Build an aligned FASTA from a query FASTA file and the SAM file "
            "produced by mapping that FASTA against a reference."
        ))

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)

        grid.addWidget(QLabel("Query FASTA:"), 0, 0)
        self.fasta_edit = QLineEdit()
        self.fasta_edit.textChanged.connect(self._on_fasta_changed)
        grid.addWidget(self.fasta_edit, 0, 1)
        btn_fasta = QPushButton("Browse...")
        btn_fasta.clicked.connect(self._browse_fasta)
        grid.addWidget(btn_fasta, 0, 2)

        grid.addWidget(QLabel("SAM file:"), 1, 0)
        self.sam_edit = QLineEdit()
        grid.addWidget(self.sam_edit, 1, 1)
        btn_sam = QPushButton("Browse...")
        btn_sam.clicked.connect(self._browse_sam)
        grid.addWidget(btn_sam, 1, 2)

        grid.addWidget(QLabel("Output FASTA:"), 2, 0)
        self.out_edit = QLineEdit()
        self.out_edit.textEdited.connect(self._mark_output_user_edited)
        grid.addWidget(self.out_edit, 2, 1)
        btn_out = QPushButton("Save as...")
        btn_out.clicked.connect(self._browse_output)
        grid.addWidget(btn_out, 2, 2)

        outer.addLayout(grid)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.button(QDialogButtonBox.Ok).setText("Create alignment")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        if fasta_path is not None:
            self.fasta_edit.setText(str(fasta_path))
            if sam_path is None:
                candidate = fasta_path.with_suffix(".sam")
                if candidate.is_file():
                    sam_path = candidate
        if sam_path is not None:
            self.sam_edit.setText(str(sam_path))

        self._update_default_output()

    # --- field handlers ----------------------------------------------------

    def _on_fasta_changed(self, _text: str) -> None:
        self._update_default_output()

    def _mark_output_user_edited(self, _text: str) -> None:
        self._user_edited_output = True

    def _update_default_output(self) -> None:
        if self._user_edited_output:
            return
        text = self.fasta_edit.text().strip()
        if not text:
            return
        p = Path(text)
        suffix = p.suffix or ".fasta"
        suggested = p.with_name(f"{p.stem}.aligned{suffix}")
        # setText doesn't fire textEdited, so the user-edited flag stays false.
        self.out_edit.setText(str(suggested))

    def _starting_dir(self) -> str:
        for candidate in (
            self.fasta_edit.text(),
            self.sam_edit.text(),
            self.out_edit.text(),
        ):
            if candidate:
                parent = Path(candidate).parent
                if parent.is_dir():
                    return str(parent)
        return ""

    def _browse_fasta(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select query FASTA", self._starting_dir(),
            "FASTA (*.fasta *.fa *.fna *.ffn *.faa *.afa *.fas *.mfa);;All files (*)",
        )
        if path:
            self.fasta_edit.setText(path)

    def _browse_sam(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SAM file", self._starting_dir(),
            "SAM (*.sam);;All files (*)",
        )
        if path:
            self.sam_edit.setText(path)

    def _browse_output(self) -> None:
        start = self.out_edit.text().strip() or self._starting_dir()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save aligned FASTA as", start,
            "FASTA (*.fasta *.fa *.afa);;All files (*)",
        )
        if path:
            self.out_edit.setText(path)
            self._user_edited_output = True

    # --- accessors --------------------------------------------------------

    def values(self) -> tuple[Path, Path, Path]:
        return (
            Path(self.fasta_edit.text().strip()),
            Path(self.sam_edit.text().strip()),
            Path(self.out_edit.text().strip()),
        )
