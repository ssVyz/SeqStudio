"""Translate between alignment coordinates (includes gaps) and sequence coordinates (ungapped).

Coordinates are 0-based internally; the ruler converts to 1-based on display.
"""
from __future__ import annotations

from bisect import bisect_right


GAP_CHARS = frozenset("-.")


class CoordinateMapper:
    """Maps a single sequence's alignment positions to its residue positions.

    Built lazily from a gapped sequence string. Memory use is O(n_residues).
    """

    __slots__ = ("_residue_to_alignment", "_alignment_length")

    def __init__(self, gapped: str):
        self._alignment_length = len(gapped)
        r2a: list[int] = []
        for i, ch in enumerate(gapped):
            if ch not in GAP_CHARS:
                r2a.append(i)
        self._residue_to_alignment = r2a

    @property
    def alignment_length(self) -> int:
        return self._alignment_length

    @property
    def ungapped_length(self) -> int:
        return len(self._residue_to_alignment)

    def alignment_to_sequence(self, col: int) -> int | None:
        """Return the 0-based residue index at alignment column `col`, or None if it's a gap."""
        if col < 0 or col >= self._alignment_length:
            return None
        idx = bisect_right(self._residue_to_alignment, col) - 1
        if idx < 0:
            return None
        if self._residue_to_alignment[idx] != col:
            return None
        return idx

    def sequence_to_alignment(self, residue_idx: int) -> int | None:
        if 0 <= residue_idx < len(self._residue_to_alignment):
            return self._residue_to_alignment[residue_idx]
        return None

    def residues_in_range(self, start_col: int, end_col: int) -> tuple[int, int]:
        """Return (first_residue, last_residue_exclusive) covered by alignment cols [start_col, end_col)."""
        left = bisect_right(self._residue_to_alignment, start_col - 1)
        right = bisect_right(self._residue_to_alignment, end_col - 1)
        return left, right
