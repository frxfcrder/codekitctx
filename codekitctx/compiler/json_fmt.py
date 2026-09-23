import json
from typing import Dict, List
from codekitctx.models import FileEntry


def render_json(files: List[FileEntry], tree: str, stats: Dict, warnings: List[str]) -> str:
    """Renders context payload into formatted JSON string."""
    payload = {
        "success": True,
        "stats": stats,
        "tree": tree,
        "warnings": warnings,
        "files": [
            {
                "path": f.relative_path,
                "language": f.language,
                "loc": f.loc,
                "content": f.content,
            }
            for f in files
        ],
    }
    return json.dumps(payload, indent=2)