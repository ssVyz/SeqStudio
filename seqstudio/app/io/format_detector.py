"""Detect the on-disk format of a sequence file."""
from __future__ import annotations

from enum import Enum
from pathlib import Path


class SequenceFormat(str, Enum):
    FASTA = "fasta"
    CLUSTAL = "clustal"
    STOCKHOLM = "stockholm"
    UNKNOWN = "unknown"


FASTA_EXTS = {".fasta", ".fa", ".fna", ".ffn", ".faa", ".afa", ".fas", ".mfa"}
CLUSTAL_EXTS = {".aln", ".clustal", ".clw"}
STOCKHOLM_EXTS = {".sto", ".stockholm", ".stk"}
TEXT_EXTS = {".txt"}


def is_sequence_file(path: Path) -> bool:
    return path.suffix.lower() in (
        FASTA_EXTS | CLUSTAL_EXTS | STOCKHOLM_EXTS
    )


def detect_format(path: Path) -> SequenceFormat:
    ext = path.suffix.lower()
    if ext in FASTA_EXTS:
        return SequenceFormat.FASTA
    if ext in CLUSTAL_EXTS:
        return SequenceFormat.CLUSTAL
    if ext in STOCKHOLM_EXTS:
        return SequenceFormat.STOCKHOLM
    return _sniff(path)


def _sniff(path: Path) -> SequenceFormat:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            head = f.read(4096)
    except OSError:
        return SequenceFormat.UNKNOWN

    if head.lstrip().startswith(">"):
        return SequenceFormat.FASTA
    if head.startswith("CLUSTAL") or head.startswith("MUSCLE"):
        return SequenceFormat.CLUSTAL
    if head.startswith("# STOCKHOLM"):
        return SequenceFormat.STOCKHOLM
    return SequenceFormat.UNKNOWN
