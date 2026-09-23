import subprocess
import sys
from typing import Optional


def copy_to_clipboard(content: str) -> bool:
    try:
        if sys.platform == "win32":
            proc = subprocess.run(
                ["clip"],
                input=content.encode("utf-16le"),
                check=True,
                timeout=5,
            )
        elif sys.platform == "darwin":
            proc = subprocess.run(
                ["pbcopy"],
                input=content.encode("utf-8"),
                check=True,
                timeout=5,
            )
        else:
            proc = subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=content.encode("utf-8"),
                check=True,
                timeout=5,
            )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False
