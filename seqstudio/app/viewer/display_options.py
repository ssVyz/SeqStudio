"""Display Options dialog: how aligned residues are rendered relative to the
consensus row (full bases vs. dots for matches)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)


class DisplayOptionsDialog(QDialog):
    def __init__(self, dots_for_matching: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Display Options")
        self.setModal(True)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "When a consensus has been calculated, draw individual sequence "
            "residues as:"
        ))

        self.radio_normal = QRadioButton("All bases normally (coloured by scheme)")
        self.radio_dots = QRadioButton(
            "Dots for bases matching the consensus (uncoloured); show "
            "differing bases normally"
        )

        group = QButtonGroup(self)
        group.addButton(self.radio_normal)
        group.addButton(self.radio_dots)

        if dots_for_matching:
            self.radio_dots.setChecked(True)
        else:
            self.radio_normal.setChecked(True)

        layout.addWidget(self.radio_normal)
        layout.addWidget(self.radio_dots)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def dots_for_matching(self) -> bool:
        return self.radio_dots.isChecked()
