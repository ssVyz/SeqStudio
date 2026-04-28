# SeqStudio

A bioinformatics-focused desktop IDE for FASTA and alignment files. Built
with PySide6, designed around a JetBrains-style layout: a file tree on the
left, a virtualised alignment viewer in the centre, and a Tool Runner dock
at the bottom.

## Features

### Viewer
- Lazy FASTA reader backed by a byte-offset index (`.ssidx` sidecar): only
  the sequences whose cells are visible are read from disk, so multi-MB
  files open instantly.
- Native readers for CLUSTAL (`.aln`) and Stockholm (`.sto`) via Biopython.
- Virtualised painter — only the cells inside the viewport are drawn, so
  rendering stays O(visible cells) regardless of alignment size.
- Synchronised tracks: column ruler, consensus row, conservation
  (identity/entropy) histogram, and a minimap "overview" for whole-file
  navigation.
- Per-residue colour schemes; optional conservation-driven background.
- Find motif (highlights matches), Go-to column, click-to-select column,
  rectangular selection, copy selection as FASTA.
- Mouse-wheel scroll (vertical), Shift+wheel (horizontal),
  Ctrl+wheel zoom.

### Consensus
- User-triggered via **Calculate Consensus** (toolbar / File menu /
  `Ctrl+Shift+K`); the user explicitly decides when to treat an open file
  as aligned, so files like `.afa` that auto-detection misjudges still
  work.
- Coverage threshold spinbox (`0.00 – 100.00 %`, two decimals): for each
  column, the smallest set of residues whose cumulative non-gap frequency
  reaches that percentage is collapsed to the matching IUPAC ambiguity
  code (worst case `N`).
- Gap-dominated columns collapse to `-`.
- Background QThread worker; result piped back to the GUI via signals.

### Display options (Settings → Display options...)
- Show all bases normally, **or** show a `.` for residues that match the
  consensus at that column.
- Dot-mode renders only when the consensus column is an unambiguous base
  (`A/C/G/T/U`) — IUPAC ambiguity columns always show real bases.
- Dot cells use a light-grey background so they are visually distinct
  from white gaps.

### Tool Runner (bottom dock)
- Curated set of external CLIs (Clustal Omega, MAFFT, MUSCLE, minimap2,
  BLAST+, trimAl, IQ-TREE).
- Detects which binaries are installed and exposes a one-click run with
  input file(s) selected from the file browser.

## Install / run

```sh
uv run main.py            # development run
uv run seqstudio          # via the project script
uv run main.py <folder>   # open a folder on launch
```

Requires Python ≥ 3.12, PySide6, Biopython.

## Project structure

```
seqstudio/
  __main__.py                # entry point, QApplication bootstrap
  app/
    window.py                # MainWindow: docks, toolbar, menus
    file_browser.py          # left dock — folder tree
    settings.py              # QSettings wrappers (persisted prefs)
    io/
      format_detector.py     # extension + content sniffing
      fasta_reader.py        # LazyFastaReader, slice-on-demand
    models/
      index.py               # FastaIndex + .ssidx sidecar
      sequence_document.py   # uniform model over FASTA/CLUSTAL/Stockholm
      coordinate_mapper.py   # alignment ↔ ungapped sequence positions
    viewer/
      alignment_view.py      # composite widget — scrollbars + grid layout
      canvas.py              # virtualised QPainter renderer
      view_state.py          # shared zoom/scroll/selection/scheme state
      ruler.py               # column-coordinate ruler
      name_panel.py          # row-id panel (left of canvas)
      consensus.py           # threaded consensus + IUPAC mapping
      conservation.py        # threaded entropy/identity histogram
      minimap.py             # whole-alignment overview
      colors.py              # residue colour schemes
      display_options.py     # dialog: bases vs dots
    tools/
      tool_definition.py     # CURATED_TOOLS catalogue
      tool_discovery.py      # which binaries exist on PATH
      tool_runner.py         # build + spawn subprocess
      runner_widget.py       # bottom dock UI
```

## Technical notes

- **Lazy I/O.** `FastaIndex` records `(seq_offset, seq_end, seq_length)`
  per record on first open and persists as a JSON sidecar
  (`<file>.fasta.ssidx`) keyed by `(size, mtime)`. `LazyFastaReader`
  seeks into the FASTA and decodes only the requested record, with a
  bounded LRU cache of recent residue strings.
- **Virtualised rendering.** `AlignmentCanvas` keeps logical scroll
  offsets in `ViewState`, computes `visible_rows()` / `visible_cols()`
  per `paintEvent`, and only fills cells inside that window. Zoom
  changes `cell_width` / `cell_height`; the same painter handles
  conservation backgrounds, search highlights, selection rectangles,
  and the consensus-dot overlay.
- **Background workers.** Consensus and conservation each run on a
  `QThread` worker that emits `result` / `chunk_ready` signals. The
  hosting widget owns the thread, captures the local references in
  `cancel()` before issuing `quit()`, and clears them again from the
  `finished` slot — so consecutive recomputes never touch a deleted
  C++ thread wrapper.
- **Consensus algorithm.** Per column: drop gaps if their fraction
  exceeds `gap_threshold`; otherwise sort non-gap residues by descending
  count, accumulate until cumulative frequency reaches the requested
  coverage, then map the resulting set to its IUPAC code. A reverse map
  (`IUPAC_EXPAND`) lets the canvas decide whether a residue "matches"
  an ambiguous consensus letter for dot-mode rendering.
- **Tool runner.** `tool_discovery` probes `PATH` for each binary in
  `CURATED_TOOLS` once at startup; `tool_runner` builds an argv from a
  `ToolDefinition`, spawns it via `QProcess`, and streams stdout/stderr
  back to the dock.
- **Persistence.** `seqstudio/app/settings.py` wraps `QSettings` for
  the last-opened folder, colour scheme, consensus coverage %, and
  dot-mode toggle.
