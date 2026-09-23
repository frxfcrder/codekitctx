from typing import Dict, List
from codekitctx.models import FileEntry


def render_markdown(
    files: List[FileEntry],
    tree: str,
    stats: Dict,
) -> str:
    """Render codebase analysis into structured Markdown."""
    out: List[str] = []

    if stats:
        out.append("## PROJECT STATS")
        out.append(f"Total Files: {stats.get('total_files', 0)}")
        out.append(f"Total LOC: {stats.get('total_loc', 0)}")
        out.append("Languages:")

        for lang, pct in stats.get("languages", {}).items():
            out.append(f"  - {lang}: {int(pct * 100)}%")

        out.append("")

    if tree:
        out.append("## PROJECT STRUCTURE")
        out.append(tree)
        out.append("")

    out.append("## CODEBASE SOURCE FILES")

    for f in files:
        out.append(f'<file path="{f.relative_path}">')
        out.append(f.content or "")
        out.append("</file>")
        out.append("")

    return "\n".join(out)