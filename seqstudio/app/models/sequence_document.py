"""SequenceDocument: the in-memory model of an opened sequence/alignment file.

Holds a lazy reader and exposes a uniform API for the viewer: number of rows,
name lookup, residue slices, etc. For aligned files `sequences_gapped()` returns
the original characters as stored; for unaligned files the residues are the
sequence itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from seqstudio.app.io.fasta_reader import LazyFastaReader
from seqstudio.app.io.format_detector import SequenceFormat, detect_format
from seqstudio.app.models.coordinate_mapper import CoordinateMapper
from seqstudio.app.models.index import IndexEntry


@dataclass
class SequenceRow:
    id: str
    description: str
    length: int


@dataclass
class SequenceDocument:
    source_path: Path
    format: SequenceFormat
    is_aligned: bool
    alignment_length: int | None
    rows: list[SequenceRow] = field(default_factory=list)
    _reader: LazyFastaReader | None = None
    _in_memory: list[str] | None = None
    _mappers: dict[int, CoordinateMapper] = field(default_factory=dict)

    @classmethod
    def open(cls, path: Path) -> "SequenceDocument":
        fmt = detect_format(path)
        if fmt == SequenceFormat.FASTA:
            return cls._open_fasta(path)
        if fmt == SequenceFormat.CLUSTAL:
            return cls._open_clustal(path)
        if fmt == SequenceFormat.STOCKHOLM:
            return cls._open_stockholm(path)
        raise ValueError(f"Unsupported or unrecognized format: {path}")

    @classmethod
    def _open_fasta(cls, path: Path) -> "SequenceDocument":
        reader = LazyFastaReader(path)
        rows = [SequenceRow(id=e.id, description=e.description, length=e.seq_length)
                for e in reader.entries]
        return cls(
            source_path=path,
            format=SequenceFormat.FASTA,
            is_aligned=reader.is_aligned,
            alignment_length=reader.alignment_length,
            rows=rows,
            _reader=reader,
        )

    @classmethod
    def _open_clustal(cls, path: Path) -> "SequenceDocument":
        from Bio import AlignIO
        alignment = AlignIO.read(str(path), "clustal")
        seqs = [str(rec.seq) for rec in alignment]
        rows = [SequenceRow(id=rec.id, description=rec.description, length=len(s))
                for rec, s in zip(alignment, seqs)]
        aln_len = len(seqs[0]) if seqs else 0
        return cls(
            source_path=path,
            format=SequenceFormat.CLUSTAL,
            is_aligned=True,
            alignment_length=aln_len,
            rows=rows,
            _in_memory=seqs,
        )

    @classmethod
    def _open_stockholm(cls, path: Path) -> "SequenceDocument":
        from Bio import AlignIO
        alignment = AlignIO.read(str(path), "stockholm")
        seqs = [str(rec.seq) for rec in alignment]
        rows = [SequenceRow(id=rec.id, description=rec.description, length=len(s))
                for rec, s in zip(alignment, seqs)]
        aln_len = len(seqs[0]) if seqs else 0
        return cls(
            source_path=path,
            format=SequenceFormat.STOCKHOLM,
            is_aligned=True,
            alignment_length=aln_len,
            rows=rows,
            _in_memory=seqs,
        )

    # --- Data access --------------------------------------------------------

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def display_length(self) -> int:
        """Columns to render — alignment length if aligned, else longest sequence."""
        if self.alignment_length is not None:
            return self.alignment_length
        return max((r.length for r in self.rows), default=0)

    def sequence(self, row: int) -> str:
        if self._in_memory is not None:
            return self._in_memory[row]
        assert self._reader is not None
        return self._reader.sequence(row)

    def slice(self, row: int, start: int, end: int) -> str:
        seq = self.sequence(row)
        if start < 0:
            start = 0
        if end > len(seq):
            end = len(seq)
        if end <= start:
            return ""
        return seq[start:end]

    def mapper(self, row: int) -> CoordinateMapper:
        m = self._mappers.get(row)
        if m is None:
            m = CoordinateMapper(self.sequence(row))
            self._mappers[row] = m
        return m

    def iter_rows(self, rows: Iterable[int]) -> Iterable[str]:
        for r in rows:
            yield self.sequence(r)

    # --- Mutation -----------------------------------------------------------

    def delete_rows(self, rows: Iterable[int]) -> int:
        """Delete the given rows from the source file in place.

        FASTA only: byte ranges of deleted entries are skipped while the rest
        of the file is rewritten verbatim, preserving original formatting.
        Returns the number of rows actually deleted.
        """
        if self.format != SequenceFormat.FASTA:
            raise NotImplementedError(
                f"Deleting sequences is currently supported only for FASTA "
                f"files (got {self.format.name})."
            )
        if self._reader is None:
            raise RuntimeError("FASTA document has no reader.")

        rows_to_delete = sorted({r for r in rows if 0 <= r < len(self.rows)})
        if not rows_to_delete:
            return 0
        if len(rows_to_delete) >= len(self.rows):
            raise ValueError(
                "Refusing to delete every sequence — that would empty the file."
            )

        entries = self._reader.entries
        delete_set = set(rows_to_delete)
        file_size = self.source_path.stat().st_size

        # Compute the byte ranges to KEEP by walking entries and excising the
        # [header_offset, seq_end) span of each deleted record.
        keep_ranges: list[tuple[int, int]] = []
        cursor = 0
        for i, entry in enumerate(entries):
            if i in delete_set:
                if entry.header_offset > cursor:
                    keep_ranges.append((cursor, entry.header_offset))
                cursor = entry.seq_end
        if cursor < file_size:
            keep_ranges.append((cursor, file_size))

        # Atomic rewrite via tmp + replace.
        tmp = self.source_path.with_name(self.source_path.name + ".tmp")
        try:
            with self.source_path.open("rb") as src, tmp.open("wb") as dst:
                for start, end in keep_ranges:
                    src.seek(start)
                    remaining = end - start
                    while remaining > 0:
                        chunk = src.read(min(remaining, 1024 * 1024))
                        if not chunk:
                            break
                        dst.write(chunk)
                        remaining -= len(chunk)
            tmp.replace(self.source_path)
        except Exception:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            raise

        # Invalidate sidecar and rebuild the in-memory state from disk.
        from seqstudio.app.models.index import sidecar_path
        sp = sidecar_path(self.source_path)
        try:
            if sp.exists():
                sp.unlink()
        except OSError:
            pass

        self._reader = LazyFastaReader(self.source_path)
        self.rows = [
            SequenceRow(id=e.id, description=e.description, length=e.seq_length)
            for e in self._reader.entries
        ]
        self.is_aligned = self._reader.is_aligned
        self.alignment_length = self._reader.alignment_length
        self._mappers.clear()
        self._in_memory = None

        return len(rows_to_delete)
