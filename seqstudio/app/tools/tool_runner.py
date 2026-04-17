"""External-terminal handoff for commands built in the Tool Runner.

SeqStudio has zero interest in tracking processes. It only:
  1. Assembles a command string from the Tool Runner UI.
  2. Opens the OS default terminal with that command pre-typed/executed,
     in the given working directory.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path


def open_in_terminal(command: str, cwd: Path) -> None:
    """Open the OS default terminal with `command` ready to run in `cwd`."""
    cwd_str = str(cwd)
    if sys.platform.startswith("win"):
        _open_windows(command, cwd_str)
    elif sys.platform == "darwin":
        _open_macos(command, cwd_str)
    else:
        _open_linux(command, cwd_str)


def _open_windows(command: str, cwd: str) -> None:
    import shutil
    wt = shutil.which("wt.exe") or shutil.which("wt")
    # Keep the window open after the command finishes so the user can see output.
    keep = f'cmd.exe /K "{command}"'
    if wt:
        subprocess.Popen([wt, "-d", cwd, "cmd.exe", "/K", command], close_fds=True)
        return
    subprocess.Popen(
        ["cmd.exe", "/C", f'start "SeqStudio" cmd.exe /K "cd /d {cwd} && {command}"'],
        close_fds=True, shell=False,
    )


def _open_macos(command: str, cwd: str) -> None:
    escaped = command.replace('"', '\\"')
    script = f'tell application "Terminal" to do script "cd {shlex.quote(cwd)} && {escaped}"'
    subprocess.Popen(["osascript", "-e", script], close_fds=True)


def _open_linux(command: str, cwd: str) -> None:
    import shutil
    terminal = os.environ.get("TERMINAL")
    candidates = [terminal] if terminal else []
    candidates += [
        "x-terminal-emulator", "gnome-terminal", "konsole",
        "xfce4-terminal", "alacritty", "kitty", "xterm",
    ]
    bash_cmd = f'cd {shlex.quote(cwd)} && {command}; exec $SHELL'
    for t in candidates:
        if not t or shutil.which(t) is None:
            continue
        try:
            if t in ("gnome-terminal",):
                subprocess.Popen([t, "--", "bash", "-lc", bash_cmd], close_fds=True)
            elif t == "konsole":
                subprocess.Popen([t, "-e", "bash", "-lc", bash_cmd], close_fds=True)
            else:
                subprocess.Popen([t, "-e", "bash", "-lc", bash_cmd], close_fds=True)
            return
        except OSError:
            continue
    # Last-ditch: run in the current shell (blocking). Only if no terminal exists.
    subprocess.Popen(["bash", "-lc", bash_cmd], close_fds=True, cwd=cwd)
