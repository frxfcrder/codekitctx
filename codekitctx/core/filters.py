from pathlib import Path
from typing import List, Optional, Tuple
from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

from codekitctx.models import SkipReason


class FilterManager:
    def __init__(
        self,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
    ):
        self.include_spec = (
            PathSpec.from_lines(GitWildMatchPattern, include)
            if include
            else None
        )
        self.exclude_spec = (
            PathSpec.from_lines(GitWildMatchPattern, exclude)
            if exclude
            else None
        )

    def evaluate(self, rel_path: Path) -> Tuple[bool, Optional[SkipReason]]:
        path_str = str(rel_path).replace("\\", "/")

        if self.exclude_spec and self.exclude_spec.match_file(path_str):
            return False, SkipReason.IGNORED

        if self.include_spec and not self.include_spec.match_file(path_str):
            return False, SkipReason.IGNORED

        return True, None

    def should_evaluate(self, rel_path: Path) -> bool:
        included, _ = self.evaluate(rel_path)
        return included