from pathlib import Path
from typing import Any, Dict, List

from codekitctx.models import FileEntry


class TreeBuilder:
    def build(self, files: List[FileEntry]) -> str:
        if not files:
            return "```\n(No files included)\n```"

        tree_dict: Dict[str, Any] = {}

        for file in files:
            parts = Path(file.relative_path).parts
            current = tree_dict
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]

        lines: List[str] = []
        self._render(tree_dict, lines, "", is_last=True)
        return "```\n" + "\n".join(lines) + "\n```"
    

    def _render(
        self, node: Dict[str, Any], lines: List[str], prefix: str, is_last: bool
    ) -> None:
        children = list(node.keys())
        for i, name in enumerate(children):
            last = i == len(children) - 1
            connector = "└── " if last else "├── "
            lines.append(f"{prefix}{connector}{name}")
            child_prefix = prefix + ("    " if last else "│   ")
            if node[name]:
                self._render(node[name], lines, child_prefix, last)
