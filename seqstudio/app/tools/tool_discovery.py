"""PATH scanning for curated tool binaries."""
from __future__ import annotations

import shutil
from dataclasses import dataclass

from seqstudio.app.tools.tool_definition import CURATED_TOOLS, ToolDefinition


@dataclass
class ToolStatus:
    definition: ToolDefinition
    path: str | None

    @property
    def installed(self) -> bool:
        return self.path is not None


def scan_tools() -> list[ToolStatus]:
    return [ToolStatus(tool, shutil.which(tool.binary)) for tool in CURATED_TOOLS]


def fetch_help_text(binary: str, timeout: float = 3.0) -> str:
    """Best-effort retrieval of `<binary> --help` output. Returns empty on error."""
    import subprocess
    if shutil.which(binary) is None:
        return ""
    for flag in ("--help", "-h", "-help"):
        try:
            proc = subprocess.run(
                [binary, flag],
                capture_output=True, text=True, timeout=timeout, check=False,
            )
            text = (proc.stdout or "") + (proc.stderr or "")
            if text.strip():
                return text
        except (OSError, subprocess.TimeoutExpired):
            continue
    return ""
