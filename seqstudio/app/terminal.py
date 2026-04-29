"""Open the OS default terminal in a given working directory."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path


def open_terminal_in(cwd: Path) -> None:
    cwd_str = str(cwd)
    if sys.platform.startswith("win"):
        _open_windows(cwd_str)
    elif sys.platform == "darwin":
        _open_macos(cwd_str)
    else:
        _open_linux(cwd_str)


def _open_windows(cwd: str) -> None:
    import shutil
    wt = shutil.which("wt.exe") or shutil.which("wt")
    if wt:
        subprocess.Popen([wt, "-d", cwd], close_fds=True)
        return
    subprocess.Popen(
        ["cmd.exe", "/C", f'start "SeqStudio" cmd.exe /K "cd /d {cwd}"'],
        close_fds=True, shell=False,
    )


def _open_macos(cwd: str) -> None:
    script = f'tell application "Terminal" to do script "cd {shlex.quote(cwd)}"'
    subprocess.Popen(["osascript", "-e", script], close_fds=True)


def _open_linux(cwd: str) -> None:
    import shutil
    terminal = os.environ.get("TERMINAL")
    candidates = [terminal] if terminal else []
    candidates += [
        "x-terminal-emulator", "gnome-terminal", "konsole",
        "xfce4-terminal", "alacritty", "kitty", "xterm",
    ]
    for t in candidates:
        if not t or shutil.which(t) is None:
            continue
        try:
            subprocess.Popen([t], cwd=cwd, close_fds=True)
            return
        except OSError:
            continue
    subprocess.Popen(["bash"], cwd=cwd, close_fds=True)
