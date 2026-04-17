"""Color schemes for residue rendering."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class ColorScheme:
    name: str
    background: dict[str, QColor]
    text: QColor
    default_bg: QColor

    def background_for(self, ch: str) -> QColor:
        c = self.background.get(ch.upper())
        return c if c is not None else self.default_bg


def _c(hex_: str) -> QColor:
    return QColor(hex_)


STANDARD_NUCLEOTIDE = ColorScheme(
    name="Standard (nucleotide)",
    background={
        "A": _c("#8ad68a"),
        "T": _c("#f08a8a"),
        "U": _c("#f08a8a"),
        "G": _c("#f0d988"),
        "C": _c("#8ab8f0"),
        "N": _c("#d0d0d0"),
        "-": _c("#ffffff"),
        ".": _c("#ffffff"),
    },
    text=_c("#000000"),
    default_bg=_c("#ececec"),
)


GRAYSCALE = ColorScheme(
    name="Grayscale",
    background={
        "A": _c("#dcdcdc"),
        "T": _c("#bfbfbf"),
        "U": _c("#bfbfbf"),
        "G": _c("#a0a0a0"),
        "C": _c("#858585"),
        "N": _c("#efefef"),
        "-": _c("#ffffff"),
        ".": _c("#ffffff"),
    },
    text=_c("#000000"),
    default_bg=_c("#efefef"),
)


PLAIN = ColorScheme(
    name="No colour",
    background={},
    text=_c("#000000"),
    default_bg=_c("#ffffff"),
)


SCHEMES: dict[str, ColorScheme] = {
    STANDARD_NUCLEOTIDE.name: STANDARD_NUCLEOTIDE,
    GRAYSCALE.name: GRAYSCALE,
    PLAIN.name: PLAIN,
}


def scheme_names() -> list[str]:
    return list(SCHEMES.keys())


def get_scheme(name: str) -> ColorScheme:
    return SCHEMES.get(name, STANDARD_NUCLEOTIDE)
