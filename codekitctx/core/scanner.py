import os
from pathlib import Path
from typing import List, Optional, Set, Tuple

from pathspec import PathSpec
from pathspec.patterns.gitwildmatch import GitWildMatchPattern

from codekitctx.models import ContextRequest, FileEntry, SkipReason

SENSITIVE_PATTERNS = {".env", ".env.*", "*.pem", "*.key", "credentials.*", "secrets.*"}


class RepositoryScanner:
    def __init__(self, req: ContextRequest):
        self.root_path = Path(req.repo_path).resolve()
        self.req = req
        self.warnings: List[str] = []

        ignore_patterns = [".git/", "node_modules/", "dist/", "build/", "__pycache__/", "target/"]
        gitignore_file = self.root_path / ".gitignore"
        if gitignore_file.exists():
            with open(gitignore_file, "r", encoding="utf-8", errors="ignore") as f:
                ignore_patterns.extend(line.strip() for line in f if line.strip())

        self.ignore_spec = PathSpec.from_lines(GitWildMatchPattern, ignore_patterns)
        self.include_spec = PathSpec.from_lines(GitWildMatchPattern, req.include) if req.include else None
        self.exclude_spec = PathSpec.from_lines(GitWildMatchPattern, req.exclude) if req.exclude else None
        self.sensitive_spec = PathSpec.from_lines(GitWildMatchPattern, SENSITIVE_PATTERNS)
        self.requested_files: Optional[Set[str]] = (
            {p.replace("\\", "/").lstrip("./") for p in req.files} if req.files else None
        )

    def scan(self) -> Tuple[List[FileEntry], int, int]:
        entries: List[FileEntry] = []
        scanned = 0
        skipped = 0

        if self.requested_files is not None:
            candidates = self._explicit_candidates()
        else:
            candidates = self._walk_candidates()

        for full_path, rel_str in candidates:
            entry, skip_reason = self._process_file(full_path, rel_str, explicit=self.requested_files is not None)
            if skip_reason is not None:
                skipped += 1
            else:
                scanned += 1
            entries.append(entry)

        return entries, scanned, skipped

    def _explicit_candidates(self) -> List[Tuple[Path, str]]:
        candidates: List[Tuple[Path, str]] = []
        assert self.requested_files is not None
        for rel in sorted(self.requested_files):
            full_path = (self.root_path / rel).resolve()
            if not str(full_path).startswith(str(self.root_path)):
                self.warnings.append(f"Skipped path outside repository: {rel}")
                continue
            if not full_path.is_file():
                self.warnings.append(f"Requested file not found: {rel}")
                continue
            candidates.append((full_path, rel))
        return candidates

    def _walk_candidates(self) -> List[Tuple[Path, str]]:
        candidates: List[Tuple[Path, str]] = []
        for root, dirs, filenames in os.walk(self.root_path):
            rel_root = Path(root).relative_to(self.root_path)
            dirs[:] = [d for d in dirs if not self._is_ignored(rel_root / d, is_dir=True)]

            for filename in filenames:
                rel_path = rel_root / filename
                rel_str = str(rel_path).replace("\\", "/")
                full_path = Path(root) / filename
                candidates.append((full_path, rel_str))
        return candidates

    def _process_file(
        self, full_path: Path, rel_str: str, *, explicit: bool
    ) -> Tuple[FileEntry, Optional[SkipReason]]:
        try:
            file_size = full_path.stat().st_size
        except OSError:
            return self._skipped_entry(full_path, rel_str, 0, SkipReason.READ_ERROR), SkipReason.READ_ERROR

        lang = self._detect_language(full_path)

        if not explicit and self._is_ignored(full_path.relative_to(self.root_path)):
            return self._skipped_entry(full_path, rel_str, file_size, SkipReason.IGNORED), SkipReason.IGNORED

        if self.sensitive_spec.match_file(rel_str) and not self.req.allow_sensitive:
            self.warnings.append(f"Skipped sensitive file: {rel_str}")
            return self._skipped_entry(full_path, rel_str, file_size, SkipReason.SENSITIVE), SkipReason.SENSITIVE

        if file_size > self.req.max_size:
            self.warnings.append(f"Skipped large file (> {self.req.max_size} bytes): {rel_str}")
            return self._skipped_entry(full_path, rel_str, file_size, SkipReason.TOO_LARGE), SkipReason.TOO_LARGE

        if lang == "Other" and not explicit:
            return self._skipped_entry(full_path, rel_str, file_size, SkipReason.UNSUPPORTED), SkipReason.UNSUPPORTED

        try:
            raw = full_path.read_bytes()
        except OSError:
            return self._skipped_entry(full_path, rel_str, file_size, SkipReason.READ_ERROR), SkipReason.READ_ERROR

        if self._is_binary(raw):
            return self._skipped_entry(full_path, rel_str, file_size, SkipReason.BINARY), SkipReason.BINARY

        try:
            content = raw.decode("utf-8", errors="replace")
            loc = len(content.splitlines())
        except Exception:
            content = ""
            loc = 0

        return (
            FileEntry(
                path=full_path,
                relative_path=rel_str,
                size_bytes=file_size,
                language=lang,
                loc=loc,
                content=content,
            ),
            None,
        )

    @staticmethod
    def _skipped_entry(
        full_path: Path, rel_str: str, file_size: int, reason: SkipReason
    ) -> FileEntry:
        return FileEntry(
            path=full_path,
            relative_path=rel_str,
            size_bytes=file_size,
            language=RepositoryScanner._detect_language(full_path),
            loc=0,
            content=None,
            is_skipped=True,
            skip_reason=reason,
        )

    def _is_ignored(self, rel_path: Path, is_dir: bool = False) -> bool:
        path_str = str(rel_path).replace("\\", "/")
        if is_dir and not path_str.endswith("/"):
            path_str += "/"

        if self.ignore_spec.match_file(path_str):
            return True
        if self.exclude_spec and self.exclude_spec.match_file(path_str):
            return True
        if is_dir:
            return False
        if self.include_spec and not self.include_spec.match_file(path_str):
            return True
        return False

    @staticmethod
    def _detect_language(path: Path) -> str:
        name = path.name.lower()

        special_names = {
            "dockerfile": "Dockerfile",
            "containerfile": "Dockerfile",
            "makefile": "Makefile",
            "gnumakefile": "Makefile",
            "cmakelists.txt": "CMake",
            "gemfile": "Ruby",
            "rakefile": "Ruby",
            "guardfile": "Ruby",
            "vagrantfile": "Ruby",
            "brewfile": "Ruby",
            "pipfile": "Python",
            "jenkinsfile": "Groovy",
            "justfile": "Just",
            "recipefile": "Just",
            "cargo.toml": "Rust",
            "go.mod": "Go",
            "go.sum": "Go",
            "gitignore": "Ignore",
            "dockerignore": "Ignore",
            "npmignore": "Ignore",
            "env": "dotenv",
        }

        if name in special_names:
            return special_names[name]

        # Dockerfile.dev, Makefile.am, ...
        for prefix in ("dockerfile", "containerfile", "makefile"):
            if name.startswith(prefix):
                return special_names[prefix]

        ext_map = {
            # Python
            ".py": "Python",
            ".pyw": "Python",
            ".pyi": "Python",

            # JavaScript / TypeScript
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".mjs": "JavaScript",
            ".cjs": "JavaScript",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".mts": "TypeScript",
            ".cts": "TypeScript",

            # Rust
            ".rs": "Rust",

            # Go
            ".go": "Go",

            # C / C++
            ".c": "C",
            ".h": "C",
            ".cc": "C++",
            ".cpp": "C++",
            ".cxx": "C++",
            ".hpp": "C++",
            ".hh": "C++",
            ".hxx": "C++",

            # Java / JVM
            ".java": "Java",
            ".kt": "Kotlin",
            ".kts": "Kotlin",
            ".scala": "Scala",
            ".sc": "Scala",
            ".groovy": "Groovy",

            # C#
            ".cs": "C#",
            ".csx": "C#",

            # Swift / Objective-C
            ".swift": "Swift",
            ".m": "Objective-C",
            ".mm": "Objective-C++",

            # PHP
            ".php": "PHP",
            ".phtml": "PHP",

            # Ruby
            ".rb": "Ruby",
            ".rake": "Ruby",
            ".gemspec": "Ruby",

            # Dart
            ".dart": "Dart",

            # Elixir / Erlang
            ".ex": "Elixir",
            ".exs": "Elixir",
            ".erl": "Erlang",
            ".hrl": "Erlang",

            # Functional
            ".hs": "Haskell",
            ".lhs": "Haskell",
            ".ml": "OCaml",
            ".mli": "OCaml",
            ".clj": "Clojure",
            ".cljs": "ClojureScript",

            # Shell
            ".sh": "Shell",
            ".bash": "Shell",
            ".zsh": "Shell",
            ".fish": "Fish",
            ".ps1": "PowerShell",
            ".psm1": "PowerShell",
            ".bat": "Batch",
            ".cmd": "Batch",

            # SQL / Database
            ".sql": "SQL",
            ".graphql": "GraphQL",
            ".gql": "GraphQL",

            # Web
            ".html": "HTML",
            ".htm": "HTML",
            ".css": "CSS",
            ".scss": "SCSS",
            ".sass": "Sass",
            ".less": "Less",
            ".vue": "Vue",
            ".svelte": "Svelte",

            # Data / Config
            ".json": "JSON",
            ".jsonc": "JSON",
            ".yaml": "YAML",
            ".yml": "YAML",
            ".toml": "TOML",
            ".xml": "XML",
            ".ini": "INI",
            ".cfg": "INI",
            ".conf": "Config",
            ".env": "dotenv",
            ".properties": "Properties",

            # Documentation
            ".md": "Markdown",
            ".mdx": "MDX",
            ".rst": "reStructuredText",
            ".txt": "Text",
            ".adoc": "AsciiDoc",

            # R / Julia
            ".r": "R",
            ".jl": "Julia",

            # Lua / Perl
            ".lua": "Lua",
            ".pl": "Perl",
            ".pm": "Perl",

            # Solidity / Web3
            ".sol": "Solidity",
            ".move": "Move",

            # Build / Infrastructure
            ".dockerfile": "Dockerfile",
            ".tf": "Terraform",
            ".tfvars": "Terraform",
            ".hcl": "HCL",

            # Make / CMake
            ".mk": "Makefile",
            ".cmake": "CMake",

            # Protobuf
            ".proto": "Protocol Buffers",

            # Assembly
            ".asm": "Assembly",
            ".s": "Assembly",

            # Vim / Emacs
            ".vim": "Vim Script",
            ".el": "Emacs Lisp",
        }

        # Dotfiles: Path(".gitignore").suffix == "", Path(".env.local").suffix == ".local"
        if name.startswith("."):
            bare = name[1:].split(".", 1)[0]
            if bare in special_names:
                return special_names[bare]
            suffix = path.suffix.lower()
            if suffix in ext_map:
                return ext_map[suffix]
            if bare == "env":
                return "dotenv"

        suffix = path.suffix.lower()
        if suffix in ext_map:
            return ext_map[suffix]

        # Compound: archive.tar.gz, etc.
        suffixes = path.suffixes
        if len(suffixes) >= 2:
            compound = "".join(suffixes[-2:]).lower()
            if compound in ext_map:
                return ext_map[compound]

        return "Other"

    @staticmethod
    def _is_binary(raw: bytes) -> bool:
        if b"\x00" in raw[:8192]:
            return True
        null_count = 0
        for byte in raw[:8192]:
            if byte == 0:
                null_count += 1
        return null_count > 1
