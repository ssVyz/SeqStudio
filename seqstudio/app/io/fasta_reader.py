"""Lazy FASTA reader backed by a byte-offset index.

Only reads the bytes of a requested sequence from disk. Uses an LRU-style
cache to keep recently-accessed sequences resident.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Iterable

from seqstudio.app.models.index import FastaIndex, IndexEntry, get_or_build_index


class LazyFastaReader:
    def __init__(self, path: Path, index: FastaIndex | None = None, cache_size: int = 512):
        self.path = Path(path)
        self.index: FastaIndex = index or get_or_build_index(self.path)
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._cache_size = cache_size
        self._id_to_entry: dict[str, IndexEntry] = {e.id: e for e in self.index.entries}

    @property
    def entries(self) -> list[IndexEntry]:
        return self.index.entries

    @property
    def is_aligned(self) -> bool:
        return self.index.is_aligned

    @property
    def alignment_length(self) -> int | None:
        return self.index.alignment_length

    def __len__(self) -> int:
        return len(self.index.entries)

    def entry(self, row: int) -> IndexEntry:
        return self.index.entries[row]

    def sequence(self, row: int) -> str:
        entry = self.entry(row)
        cached = self._cache.get(entry.id)
        if cached is not None:
            self._cache.move_to_end(entry.id)
            return cached

        with self.path.open("rb") as f:
            f.seek(entry.seq_offset)
            raw = f.read(entry.seq_end - entry.seq_offset)
        # Strip all whitespace while preserving residue/gap characters.
        seq = raw.decode("ascii", errors="replace").translate(_WHITESPACE_TABLE)

        self._cache[entry.id] = seq
        self._cache.move_to_end(entry.id)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return seq

    def sequence_slice(self, row: int, start: int, end: int) -> str:
        """Return residues [start, end) (alignment coordinates, 0-based)."""
        seq = self.sequence(row)
        if start < 0:
            start = 0
        if end > len(seq):
            end = len(seq)
        if end <= start:
            return ""
        return seq[start:end]

    def iter_sequences(self, rows: Iterable[int]) -> Iterable[str]:
        for r in rows:
            yield self.sequence(r)


_WHITESPACE_TABLE = {ord(c): None for c in " \t\r\n\v\f"}
