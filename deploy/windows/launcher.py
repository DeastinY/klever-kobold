"""What kobold.exe runs: the `kobold` command, frozen by PyInstaller.

One difference from the console-installed tool: Windows opens a console just
for a program started from a shortcut or a double-click, and closes it the
moment the program exits. A failed `serve` ("No index at ... Fetch it with:
kobold setup") would vanish unread, so when the console is ours alone, a
failure waits for a keypress.
"""

from __future__ import annotations

import contextlib
import multiprocessing
import os
import sys

from kleverkobold.__main__ import main


def own_console() -> bool:
    """True when this console has no other process in it: a shortcut, not a terminal."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        pids = (ctypes.c_uint * 2)()
        return ctypes.windll.kernel32.GetConsoleProcessList(pids, 2) <= 1
    except Exception:
        return False


if __name__ == "__main__":
    multiprocessing.freeze_support()
    code = main()
    if code and own_console():
        with contextlib.suppress(EOFError):
            input("\nPress Enter to close this window.")
    sys.exit(code)
