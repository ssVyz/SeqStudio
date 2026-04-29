"""SAM-to-MSA conversion: build an aligned FASTA from a query FASTA + a SAM file.

The user runs an external mapper (e.g. minimap2) outside SeqStudio and provides
both the original query FASTA and the resulting SAM. We:

  1. Parse both files.
  2. Validate that the two describe the same set of sequences (names + content,
     accounting for reverse-complement and hard-clipping).
  3. Reconstruct a multiple sequence alignment by walking each read's CIGAR
     against a shared reference-coordinate column system.
  4. Write the aligned FASTA.

The output sequences are oriented as they aligned to the reference: reverse-
strand reads are reverse-complemented relative to the input FASTA. Soft-clipped
and hard-clipped bases are excluded from the alignment.
"""
from __future__ import annotations

import re
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path


_CIGAR_RE = re.compile(r"(\d+)([MIDNSHP=X])")
_REF_CONSUMING = set("MDN=X")
_COMPLEMENT_TABLE = str.maketrans(
    "ACGTUNRYMKSWHBVDXacgtunrymkswhbvdx",
    "TGCAANYRKMSWDVBHXtgcaanyrkmswdvbhx",
)
_FASTA_STRIP = {ord(c): None for c in " \t\r\n\v\f-."}


def _open_text(path: Path):
    """Open a text file with BOM-aware encoding detection.

    Handles UTF-8 (with or without BOM) and UTF-16 LE/BE — PowerShell's `>`
    redirection on Windows produces UTF-16 LE with BOM, which a naive UTF-8
    open silently mangles into NUL-interleaved garbage.
    """
    with path.open("rb") as f:
        head = f.read(4)
    if head.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    elif head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        encoding = "utf-16"
    else:
        encoding = "utf-8"
    return path.open("r", encoding=encoding, errors="replace")


@dataclass
class SamRecord:
    qname: str
    flag: int
    pos: int  # 1-based leftmost reference position
    cigar: str
    seq: str

    @property
    def is_unmapped(self) -> bool:
        return bool(self.flag & 0x4)

    @property
    def is_reverse(self) -> bool:
        return bool(self.flag & 0x10)

    @property
    def is_secondary(self) -> bool:
        return bool(self.flag & 0x100)

    @property
    def is_supplementary(self) -> bool:
        return bool(self.flag & 0x800)


@dataclass
class AlignmentResult:
    output_path: Path
    aligned_count: int
    unmapped_names: list[str]
    total_columns: int


# --- parsing --------------------------------------------------------------


def parse_cigar(cigar: str) -> list[tuple[str, int]]:
    if not cigar or cigar == "*":
        return []
    return [(op, int(length)) for length, op in _CIGAR_RE.findall(cigar)]


def reverse_complement(seq: str) -> str:
    return seq.translate(_COMPLEMENT_TABLE)[::-1]


def read_fasta(path: Path) -> "OrderedDict[str, str]":
    """Read a FASTA file into name → sequence (whitespace and gaps stripped)."""
    seqs: "OrderedDict[str, str]" = OrderedDict()
    name: str | None = None
    chunks: list[str] = []
    with _open_text(path) as f:
        for line in f:
            line = line.rstrip("\r\n")
            if line.startswith(">"):
                if name is not None:
                    _store_fasta(seqs, name, chunks)
                header = line[1:].strip()
                name = header.split()[0] if header else ""
                chunks = []
            elif line:
                chunks.append(line)
        if name is not None:
            _store_fasta(seqs, name, chunks)
    return seqs


def _store_fasta(seqs: "OrderedDict[str, str]", name: str, chunks: list[str]) -> None:
    if name in seqs:
        raise ValueError(f"Duplicate FASTA sequence name: '{name}'")
    seqs[name] = "".join(chunks).translate(_FASTA_STRIP)


def read_sam(path: Path) -> list[SamRecord]:
    """Read all (non-header) records from a SAM file."""
    records: list[SamRecord] = []
    with _open_text(path) as f:
        for line in f:
            if line.startswith("@") or not line.strip():
                continue
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) < 11:
                continue
            try:
                rec = SamRecord(
                    qname=parts[0],
                    flag=int(parts[1]),
                    pos=int(parts[3]),
                    cigar=parts[5],
                    seq=parts[9],
                )
            except ValueError:
                continue
            records.append(rec)
    return records


def primary_records(records: list[SamRecord]) -> "OrderedDict[str, SamRecord]":
    """Pick one record per QNAME, preferring the first primary mapped record.

    Falls back to any record (incl. unmapped) when no mapped primary exists.
    """
    primary: "OrderedDict[str, SamRecord]" = OrderedDict()
    fallback: "OrderedDict[str, SamRecord]" = OrderedDict()
    for r in records:
        if r.is_secondary or r.is_supplementary:
            continue
        if r.qname not in fallback:
            fallback[r.qname] = r
        if not r.is_unmapped and r.qname not in primary:
            primary[r.qname] = r
    combined: "OrderedDict[str, SamRecord]" = OrderedDict()
    for name, rec in fallback.items():
        combined[name] = primary.get(name, rec)
    return combined


# --- validation -----------------------------------------------------------


@dataclass
class _ValidationCounts:
    aligned_count: int
    unmapped_names: list[str]


def validate_match(
    fasta_seqs: "OrderedDict[str, str]",
    sam_primary: "OrderedDict[str, SamRecord]",
) -> _ValidationCounts:
    """Verify FASTA and SAM agree on names and (oriented) content.

    Raises ValueError on any mismatch.
    """
    fasta_names = set(fasta_seqs.keys())
    sam_names = set(sam_primary.keys())

    missing = [n for n in fasta_seqs if n not in sam_names]
    if missing:
        raise ValueError(_format_name_error(
            "SAM file is missing entries for FASTA sequences", missing
        ))

    extra = [n for n in sam_names if n not in fasta_names]
    if extra:
        raise ValueError(_format_name_error(
            "SAM file references sequences not present in FASTA", extra
        ))

    unmapped: list[str] = []
    for name, fasta_seq in fasta_seqs.items():
        rec = sam_primary[name]
        if rec.is_unmapped:
            unmapped.append(name)
            continue
        if rec.seq == "*" or not rec.seq:
            continue
        ops = parse_cigar(rec.cigar)
        head_h = ops[0][1] if ops and ops[0][0] == "H" else 0
        tail_h = ops[-1][1] if ops and ops[-1][0] == "H" else 0
        oriented = reverse_complement(fasta_seq) if rec.is_reverse else fasta_seq
        end = len(oriented) - tail_h
        expected = oriented[head_h:end]
        if rec.seq.upper() != expected.upper():
            raise ValueError(
                f"Sequence content mismatch for '{name}': the SAM SEQ field "
                f"disagrees with the FASTA sequence (a different FASTA may "
                f"have been used as input to the aligner)."
            )

    return _ValidationCounts(
        aligned_count=len(fasta_seqs) - len(unmapped),
        unmapped_names=unmapped,
    )


def _format_name_error(prefix: str, names: list[str], cap: int = 5) -> str:
    head = ", ".join(names[:cap])
    suffix = f" and {len(names) - cap} more" if len(names) > cap else ""
    return f"{prefix} ({len(names)}): {head}{suffix}"


# --- MSA construction -----------------------------------------------------


def build_aligned_fasta(
    fasta_seqs: "OrderedDict[str, str]",
    sam_primary: "OrderedDict[str, SamRecord]",
) -> list[tuple[str, str]]:
    """Build the multiple sequence alignment.

    Returns (name, aligned_sequence) pairs in the original FASTA order.
    Unmapped sequences are excluded.
    """
    parsed: dict[str, list[tuple[str, int]]] = {}
    mapped_names: list[str] = []
    ref_min: int | None = None
    ref_max: int | None = None

    for name in fasta_seqs:
        rec = sam_primary.get(name)
        if rec is None or rec.is_unmapped:
            continue
        ops = parse_cigar(rec.cigar)
        if not ops:
            continue
        parsed[name] = ops
        rc = sum(length for op, length in ops if op in _REF_CONSUMING)
        end = rec.pos + rc - 1
        if ref_min is None or rec.pos < ref_min:
            ref_min = rec.pos
        if ref_max is None or end > ref_max:
            ref_max = end
        mapped_names.append(name)

    if ref_min is None or ref_max is None:
        return []

    # ins_after[p] = max number of inserted query bases immediately following ref pos p.
    # Insertions before the very first ref position are stored at ins_after[ref_min - 1].
    ins_after: dict[int, int] = defaultdict(int)
    for name in mapped_names:
        rec = sam_primary[name]
        cur_ref = rec.pos - 1  # last consumed reference position (1-based)
        for op, length in parsed[name]:
            if op in "MX=":
                cur_ref += length
            elif op == "I":
                if length > ins_after[cur_ref]:
                    ins_after[cur_ref] = length
            elif op in "DN":
                cur_ref += length

    # Map each ref position to its global column index.
    ref_to_col: dict[int, int] = {}
    col = ins_after[ref_min - 1]  # leading insertion columns
    for p in range(ref_min, ref_max + 1):
        ref_to_col[p] = col
        col += 1 + ins_after[p]
    total_cols = col

    aligned: list[tuple[str, str]] = []
    for name in fasta_seqs:
        ops = parsed.get(name)
        if ops is None:
            continue
        rec = sam_primary[name]

        if rec.seq and rec.seq != "*":
            query = rec.seq
        else:
            query = reverse_complement(fasta_seqs[name]) if rec.is_reverse else fasta_seqs[name]

        out: list[str] = ["-"] * total_cols
        cur_ref = rec.pos
        cur_query = 0

        for op, length in ops:
            if op in "MX=":
                for _ in range(length):
                    out[ref_to_col[cur_ref]] = query[cur_query]
                    cur_ref += 1
                    cur_query += 1
            elif op == "I":
                if cur_ref > ref_max:
                    ins_start = ref_to_col[ref_max] + 1
                else:
                    ins_start = ref_to_col[cur_ref] - ins_after[cur_ref - 1]
                for i in range(length):
                    out[ins_start + i] = query[cur_query]
                    cur_query += 1
            elif op in "DN":
                for _ in range(length):
                    out[ref_to_col[cur_ref]] = "-"
                    cur_ref += 1
            elif op == "S":
                cur_query += length
            # H, P: nothing to emit, no query/ref consumption that affects columns

        aligned.append((name, "".join(out)))

    return aligned


# --- output ---------------------------------------------------------------


def write_fasta(path: Path, sequences: list[tuple[str, str]], wrap: int = 60) -> None:
    with path.open("w", encoding="utf-8") as f:
        for name, seq in sequences:
            f.write(f">{name}\n")
            if wrap and wrap > 0:
                for i in range(0, len(seq), wrap):
                    f.write(seq[i:i + wrap])
                    f.write("\n")
            else:
                f.write(seq)
                f.write("\n")


def create_alignment_from_sam(
    fasta_path: Path,
    sam_path: Path,
    output_path: Path,
) -> AlignmentResult:
    """End-to-end conversion: query FASTA + SAM → aligned FASTA file."""
    fasta_seqs = read_fasta(fasta_path)
    if not fasta_seqs:
        raise ValueError(f"No sequences found in FASTA: {fasta_path}")

    sam_records = read_sam(sam_path)
    if not sam_records:
        raise ValueError(f"No alignment records found in SAM: {sam_path}")

    sam_primary = primary_records(sam_records)
    counts = validate_match(fasta_seqs, sam_primary)
    aligned = build_aligned_fasta(fasta_seqs, sam_primary)
    if not aligned:
        raise ValueError(
            "No mapped sequences to align — every entry in the SAM file is "
            "marked unmapped."
        )

    write_fasta(output_path, aligned)
    return AlignmentResult(
        output_path=output_path,
        aligned_count=counts.aligned_count,
        unmapped_names=counts.unmapped_names,
        total_columns=len(aligned[0][1]),
    )
