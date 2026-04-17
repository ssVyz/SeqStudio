"""SeqStudio entry point."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from seqstudio.app.window import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SeqStudio")
    app.setOrganizationName("SeqStudio")
    app.setOrganizationDomain("seqstudio.local")

    window = MainWindow()
    window.show()

    if len(sys.argv) > 1:
        window.open_folder(sys.argv[1])

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
