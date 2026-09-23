from collections import defaultdict
from typing import Any, Dict, List

from codekitctx.models import FileEntry


class StatsCalculator:
    @staticmethod
    def calculate(files: List[FileEntry]) -> Dict[str, Any]:
        total_loc = sum(f.loc for f in files)

        lang_loc: Dict[str, int] = defaultdict(int)
        for f in files:
            lang_loc[f.language] += f.loc

        languages = {
            lang: round(loc / total_loc, 4) if total_loc else 0.0
            for lang, loc in lang_loc.items()
        }

        top_files = sorted(files, key=lambda f: f.loc, reverse=True)[:5]

        return {
            "total_files": len(files),
            "total_loc": total_loc,
            "languages": languages,
            "largest_files": [{"path": f.relative_path, "loc": f.loc} for f in top_files],
        }
