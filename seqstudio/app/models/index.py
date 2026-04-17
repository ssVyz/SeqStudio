"""Byte-offset index for FASTA files.

Builds a lightweight sidecar (`.ssidx`) so re-opening a large FASTA does not
re-scan the file. Each entry records where the sequence body lives in the file
and its ungapped character count, allowing lazy reads of individual records
without loading the whole file into memory.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


SSIDX_SUFFIX = ".ssidx"
INDEX_FORMAT_VERSION = 1


@dataclass
class IndexEntry:
    id: str
    description: str
    header_offset: int
    seq_offset: int
    seq_end: int
    seq_length: int


@dataclass
class FastaIndex:
    path: str
    size: int
    mtime: float
    entries: list[IndexEntry] = field(default_factory=list)
    version: int = INDEX_FORMAT_VERSION

    @property
    def is_aligned(self) -> bool:
        if not self.entries:
            return False
        first = self.entries[0].seq_length
        return all(e.seq_length == first for e in self.entries)

    @property
    def alignment_length(self) -> int | None:
        return self.entries[0].seq_length if self.is_aligned and self.entries else None

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "path": self.path,
            "size": self.size,
            "mtime": self.mtime,
            "entries": [asdict(e) for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FastaIndex":
        return cls(
            path=data["path"],
            size=data["size"],
            mtime=data["mtime"],
            version=data.get("version", INDEX_FORMAT_VERSION),
            entries=[IndexEntry(**e) for e in data["entries"]],
        )


def sidecar_path(source: Path) -> Path:
    return source.with_suffix(source.suffix + SSIDX_SUFFIX)


def load_index(source: Path) -> FastaIndex | None:
    sp = sidecar_path(source)
    if not sp.exists():
        return None
    try:
        with sp.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("version") != INDEX_FORMAT_VERSION:
        return None
    try:
        index = FastaIndex.from_dict(data)
    except (KeyError, TypeError):
        return None
    stat = source.stat()
    if index.size != stat.st_size or abs(index.mtime - stat.st_mtime) > 1e-6:
        return None
    return index


def save_index(source: Path, index: FastaIndex) -> None:
    sp = sidecar_path(source)
    tmp = sp.with_suffix(sp.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(index.to_dict(), f)
    tmp.replace(sp)


def build_index(source: Path) -> FastaIndex:
    stat = source.stat()
    entries: list[IndexEntry] = []

    current_header_offset = -1
    current_id = ""
    current_desc = ""
    current_seq_offset = 0
    current_char_count = 0

    offset = 0
    with source.open("rb") as f:
        for raw_line in f:
            line_len = len(raw_line)
            if raw_line.startswith(b">"):
                if current_header_offset >= 0:
                    entries.append(IndexEntry(
                        id=current_id,
                        description=current_desc,
                        header_offset=current_header_offset,
                        seq_offset=current_seq_offset,
                        seq_end=offset,
                        seq_length=current_char_count,
                    ))
                header = raw_line[1:].rstrip(b"\r\n").decode("utf-8", errors="replace")
                sp_idx = header.find(" ")
                if sp_idx < 0:
                    sp_idx = header.find("\t")
                if sp_idx < 0:
                    current_id = header
                    current_desc = ""
                else:
                    current_id = header[:sp_idx]
                    current_desc = header[sp_idx + 1:]
                current_header_offset = offset
                current_seq_offset = offset + line_len
                current_char_count = 0
            else:
                stripped = raw_line.strip()
                current_char_count += len(stripped)
            offset += line_len

        if current_header_offset >= 0:
            entries.append(IndexEntry(
                id=current_id,
                description=current_desc,
                header_offset=current_header_offset,
                seq_offset=current_seq_offset,
                seq_end=offset,
                seq_length=current_char_count,
            ))

    return FastaIndex(
        path=str(source),
        size=stat.st_size,
        mtime=stat.st_mtime,
        entries=entries,
    )


def get_or_build_index(source: Path, save: bool = True) -> FastaIndex:
    cached = load_index(source)
    if cached is not None:
        return cached
    index = build_index(source)
    if save:
        try:
            save_index(source, index)
        except OSError:
            pass
    return index
