import asyncio
from pathlib import Path
from typing import Dict, List, Tuple

from codekitctx.compiler.json_fmt import render_json
from codekitctx.compiler.markdown import render_markdown
from codekitctx.compiler.prompt import wrap_prompt
from codekitctx.core.filters import FilterManager
from codekitctx.core.scanner import RepositoryScanner
from codekitctx.core.stats import StatsCalculator
from codekitctx.core.tree import TreeBuilder
from codekitctx.models import ContextRequest, ContextResult, FileEntry, SkipReason
from codekitctx.parser.sitter import get_parser

class Scan:
    def __init__(self, request: ContextRequest):
        self.request = request
        self.scanner = RepositoryScanner(request)

    def execute(self) -> Tuple[
        List[FileEntry],
        int,
        int,
        List[str],
    ]:
        files, scanned_count, skipped_count = self.scanner.scan()
        return files, scanned_count, skipped_count, self.scanner.warnings


class Filter:
    def __init__(self, include: List[str], exclude: List[str]):
        self.filter_mgr = FilterManager(include=include, exclude=exclude)

    def execute(
        self, scanned_files: List[FileEntry], skipped_files: List[FileEntry]
    ) -> Tuple[List[FileEntry], List[FileEntry]]:
        included: List[FileEntry] = []

        for file in scanned_files:
            rel_path = Path(file.relative_path)
            should_inc, skip_reason = self.filter_mgr.evaluate(rel_path)

            if should_inc:
                included.append(file)
            else:
                file.is_skipped = True
                file.skip_reason = skip_reason
                skipped_files.append(file)

        return included, skipped_files


class Parse:
    def __init__(self, compact_mode: bool):
        self.compact_mode = compact_mode
        self.parser = get_parser() if compact_mode else None

    def execute(self, files: List[FileEntry]) -> List[FileEntry]:
        if not self.compact_mode or not self.parser:
            return files

        for file in files:
            if file.content:
                symbols = self.parser.parse(file.content, Path(file.relative_path))
                if symbols:
                    file.content = self._symbols_to_text(symbols)

        return files

    @staticmethod
    def _symbols_to_text(symbols: List) -> str:
        lines: List[str] = []
        for s in symbols:
            prefix = f"{s.parent}." if s.parent else ""
            lines.append(f"{s.kind} {prefix}{s.name}  # L{s.line_start}-L{s.line_end}")
            for c in s.children:
                lines.append(f"  {c.kind} {prefix}{c.name}  # L{c.line_start}-L{c.line_end}")
        return "\n".join(lines)



class Stats:
    @staticmethod
    def execute(
        files: List[FileEntry], skipped_files: List[FileEntry], enabled: bool
    ) -> Tuple[Dict, Dict[str, int]]:
        stats_dict = StatsCalculator.calculate(files) if enabled else {}

        skip_breakdown: Dict[str, int] = {}
        for sf in skipped_files:
            if sf.skip_reason:
                reason_key = sf.skip_reason.value
                skip_breakdown[reason_key] = skip_breakdown.get(reason_key, 0) + 1

        return stats_dict, skip_breakdown



class Tree:
    @staticmethod
    def execute(files: List[FileEntry], enabled: bool) -> str:
        if not enabled:
            return ""
        return TreeBuilder().build(files)



class Compile:
    

    def __init__(self, output_format: str, prompt_wrap: bool):
        self.output_format = output_format.lower()
        self.prompt_wrap = prompt_wrap

    def execute(
        self,
        files: List[FileEntry],
        tree: str,
        stats: Dict,
        warnings: List[str],
    ) -> str:
        if self.output_format == "json":
            output_content = render_json(files, tree, stats, warnings)
        else:
            output_content = render_markdown(files, tree, stats)

        if self.prompt_wrap:
            output_content = wrap_prompt(output_content)

        return output_content



class RepoContext:
    

    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    def compile(self, **kwargs) -> ContextResult:
        req = ContextRequest(repo_path=self.repo_path, **kwargs)

        # Stage 1: Scan
        scanned_files, total_scanned, total_skipped, warnings = Scan(req).execute()

        # Stage 2: Filter
        included, all_skipped = Filter(req.include, req.exclude).execute(scanned_files, [])

        # Stage 3: Parse
        parsed_files = Parse(req.compact).execute(included)

        # Stage 4: Stats
        stats_dict, skip_breakdown = Stats.execute(parsed_files, all_skipped, req.stats)

        # Stage 5: Tree
        tree_str = Tree.execute(parsed_files, req.tree)

        # Stage 6: Compile
        compiled_output = Compile(req.format, req.prompt).execute(
            parsed_files, tree_str, stats_dict, warnings
        )

        return ContextResult(
            success=True,
            markdown=compiled_output,
            stats=stats_dict,
            tree=tree_str,
            files_scanned=total_scanned,
            files_skipped=len(all_skipped),
            skipped_breakdown=skip_breakdown,
            warnings=warnings,
        )


class AsyncRepoContext(RepoContext):
    async def compile_async(self, **kwargs) -> ContextResult:
        return await asyncio.to_thread(self.compile, **kwargs)