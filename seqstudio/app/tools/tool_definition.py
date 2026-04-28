"""Curated tool definitions for the Tool Runner."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    binary: str
    install_url: str
    input_flag: str = "-i"
    output_flag: str = "-o"
    multi_input: bool = False
    defaults: str = ""
    output_suffix: str = "_out.fasta"


CURATED_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="Clustal Omega",
        binary="clustalo",
        install_url="http://www.clustal.org/omega/",
        input_flag="-i",
        output_flag="-o",
        defaults="--threads=4 --force",
        output_suffix="_clustalo.fasta",
    ),
    ToolDefinition(
        name="MAFFT",
        binary="mafft",
        install_url="https://mafft.cbrc.jp/alignment/software/",
        input_flag="",           # mafft takes input as positional
        output_flag=">",         # redirected to stdout
        defaults="--auto",
        output_suffix="_mafft.fasta",
    ),
    ToolDefinition(
        name="MUSCLE",
        binary="muscle",
        install_url="https://drive5.com/muscle/",
        input_flag="-in",
        output_flag="-out",
        defaults="",
        output_suffix="_muscle.fasta",
    ),
    ToolDefinition(
        name="minimap2",
        binary="minimap2",
        install_url="https://github.com/lh3/minimap2",
        input_flag="",
        output_flag=">",
        defaults="-a",
        output_suffix=".sam",
        multi_input=True,
    ),
    ToolDefinition(
        name="BLAST+ (blastn)",
        binary="blastn",
        install_url="https://www.ncbi.nlm.nih.gov/books/NBK279690/",
        input_flag="-query",
        output_flag="-out",
        defaults="-outfmt 6",
        output_suffix="_blastn.tsv",
    ),
    ToolDefinition(
        name="BLAST+ (makeblastdb)",
        binary="makeblastdb",
        install_url="https://www.ncbi.nlm.nih.gov/books/NBK279690/",
        input_flag="-in",
        output_flag="-out",
        defaults="-dbtype nucl",
        output_suffix="_db",
    ),
    ToolDefinition(
        name="trimAl",
        binary="trimal",
        install_url="http://trimal.cgenomics.org/",
        input_flag="-in",
        output_flag="-out",
        defaults="-automated1",
        output_suffix="_trimmed.fasta",
    ),
    ToolDefinition(
        name="IQ-TREE",
        binary="iqtree2",
        install_url="http://www.iqtree.org/",
        input_flag="-s",
        output_flag="",
        defaults="-m MFP -nt AUTO",
        output_suffix=".treefile",
    ),
    ToolDefinition(
        name="diffalign",
        binary="diffalign",
        install_url="tool_doc/diffalign_README.md",
        input_flag="",                # positional: TEMPLATE REFERENCE
        output_flag="-o",
        defaults="",                  # parameters live in diffalign.ini
        output_suffix="_diffalign.json",
    ),
]


def find_tool(binary: str) -> ToolDefinition | None:
    for t in CURATED_TOOLS:
        if t.binary == binary:
            return t
    return None
