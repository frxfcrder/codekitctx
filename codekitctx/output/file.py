from pathlib import Path
from typing import Optional


def save_to_file(content: str, output_path: str = "context-output.md", append: bool = False) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if append and path.exists():
        existing = path.read_text(encoding="utf-8")
        content = existing + "\n\n" + content

    path.write_text(content, encoding="utf-8")
    return str(path.resolve())
