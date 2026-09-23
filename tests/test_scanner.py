from pathlib import Path

import pytest

from codekitctx.core.scanner import RepositoryScanner
from codekitctx.models import ContextRequest, SkipReason


@pytest.fixture
def sample_repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello():\n    return 'hi'\n")
    (tmp_path / "src" / "utils.py").write_text("x = 1\ny = 2\n")
    (tmp_path / "README.md").write_text("# Test\n")
    (tmp_path / "data.txt").write_text("some text\n")
    return tmp_path


def make_req(repo_path, **kwargs):
    return ContextRequest(repo_path=str(repo_path), **kwargs)


class TestBasicScan:
    def test_finds_files(self, sample_repo):
        scanner = RepositoryScanner(make_req(sample_repo))
        entries, scanned, skipped = scanner.scan()
        assert scanned == 4
        assert skipped == 0
        assert len(entries) == 4

    def test_file_content_loaded(self, sample_repo):
        scanner = RepositoryScanner(make_req(sample_repo))
        entries, _, _ = scanner.scan()
        py_files = [e for e in entries if e.language == "Python"]
        assert len(py_files) == 2
        assert all(e.content for e in py_files)

    def test_loc_counted(self, sample_repo):
        scanner = RepositoryScanner(make_req(sample_repo))
        entries, _, _ = scanner.scan()
        main = next(e for e in entries if e.relative_path == "src/main.py")
        assert main.loc == 2

    def test_relative_paths(self, sample_repo):
        scanner = RepositoryScanner(make_req(sample_repo))
        entries, _, _ = scanner.scan()
        paths = {e.relative_path for e in entries}
        assert "src/main.py" in paths
        assert "README.md" in paths


class TestGitignore:
    def test_gitignored_files_skipped(self, tmp_path):
        (tmp_path / ".gitignore").write_text("secret.txt\n")
        (tmp_path / "secret.txt").write_text("hidden\n")
        (tmp_path / "visible.py").write_text("x = 1\n")

        scanner = RepositoryScanner(make_req(tmp_path))
        entries, scanned, skipped = scanner.scan()
        secret = next(e for e in entries if e.relative_path == "secret.txt")
        assert secret.is_skipped
        assert secret.skip_reason == SkipReason.IGNORED
        visible = next(e for e in entries if e.relative_path == "visible.py")
        assert not visible.is_skipped

    def test_pycache_ignored(self, tmp_path):
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "mod.pyc").write_bytes(b"\x00\x01")
        (tmp_path / "app.py").write_text("x = 1\n")

        scanner = RepositoryScanner(make_req(tmp_path))
        entries, scanned, skipped = scanner.scan()
        assert scanned == 1
        assert all("__pycache__" not in e.relative_path for e in entries)


class TestSensitiveFiles:
    def test_env_file_skipped(self, tmp_path):
        (tmp_path / ".env").write_text("SECRET=abc\n")
        (tmp_path / "app.py").write_text("x = 1\n")

        scanner = RepositoryScanner(make_req(tmp_path))
        entries, scanned, skipped = scanner.scan()
        env = next(e for e in entries if e.relative_path == ".env")
        assert env.skip_reason == SkipReason.SENSITIVE
        assert skipped == 1

    def test_allow_sensitive(self, tmp_path):
        (tmp_path / ".env").write_text("SECRET=abc\n")

        scanner = RepositoryScanner(make_req(tmp_path, allow_sensitive=True))
        _, scanned, skipped = scanner.scan()
        assert scanned == 1
        assert skipped == 0

    def test_pem_file_skipped(self, tmp_path):
        (tmp_path / "server.pem").write_text("fake cert\n")
        scanner = RepositoryScanner(make_req(tmp_path))
        entries, _, _ = scanner.scan()
        pem = next(e for e in entries if e.relative_path == "server.pem")
        assert pem.skip_reason == SkipReason.SENSITIVE


class TestSizeLimit:
    def test_large_file_skipped(self, tmp_path):
        (tmp_path / "big.py").write_text("x" * 100)
        (tmp_path / "small.py").write_text("x = 1\n")

        scanner = RepositoryScanner(make_req(tmp_path, max_size=50))
        entries, scanned, skipped = scanner.scan()
        assert skipped == 1
        big = next(e for e in entries if e.relative_path == "big.py")
        assert big.skip_reason == SkipReason.TOO_LARGE


class TestBinaryDetection:
    def test_binary_file_skipped(self, tmp_path):
        (tmp_path / "data.py").write_bytes(b"\x00\x01\x02hello")
        (tmp_path / "code.py").write_text("x = 1\n")

        scanner = RepositoryScanner(make_req(tmp_path))
        entries, scanned, skipped = scanner.scan()
        data = next(e for e in entries if e.relative_path == "data.py")
        assert data.skip_reason == SkipReason.BINARY


class TestUnsupportedLanguage:
    def test_unknown_extension_skipped(self, tmp_path):
        (tmp_path / "mystery.xyz").write_text("hello\n")
        (tmp_path / "code.py").write_text("x = 1\n")

        scanner = RepositoryScanner(make_req(tmp_path))
        entries, scanned, skipped = scanner.scan()
        mystery = next(e for e in entries if e.relative_path == "mystery.xyz")
        assert mystery.skip_reason == SkipReason.UNSUPPORTED


class TestExplicitFiles:
    def test_only_requested_files(self, sample_repo):
        scanner = RepositoryScanner(make_req(sample_repo, files=["src/main.py"]))
        entries, scanned, skipped = scanner.scan()
        assert scanned == 1
        assert entries[0].relative_path == "src/main.py"

    def test_multiple_files(self, sample_repo):
        scanner = RepositoryScanner(
            make_req(sample_repo, files=["src/main.py", "README.md"])
        )
        _, scanned, _ = scanner.scan()
        assert scanned == 2

    def test_missing_file_warning(self, sample_repo):
        scanner = RepositoryScanner(make_req(sample_repo, files=["nope.py"]))
        _, scanned, _ = scanner.scan()
        assert scanned == 0
        assert any("not found" in w for w in scanner.warnings)

    def test_explicit_unsupported_file(self, tmp_path):
        (tmp_path / "weird.xyz").write_text("content\n")
        scanner = RepositoryScanner(make_req(tmp_path, files=["weird.xyz"]))
        entries, scanned, _ = scanner.scan()
        assert scanned == 1


class TestLanguageDetection:
    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("app.py", "Python"),
            ("main.js", "JavaScript"),
            ("index.ts", "TypeScript"),
            ("lib.rs", "Rust"),
            ("main.go", "Go"),
            ("App.java", "Java"),
            ("core.cpp", "C++"),
            ("util.h", "C"),
            ("Program.cs", "C#"),
            ("script.rb", "Ruby"),
            ("Dockerfile", "Dockerfile"),
            ("Makefile", "Makefile"),
            ("Cargo.toml", "Rust"),
            ("package.json", "JSON"),
            ("README.md", "Markdown"),
            (".gitignore", "Ignore"),
            (".env", "dotenv"),
            ("unknown.xyz", "Other"),
        ],
    )
    def test_detect_language(self, filename, expected):
        result = RepositoryScanner._detect_language(Path(filename))
        assert result == expected


class TestIncludeExclude:
    def test_include_patterns(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.js").write_text("x = 1;\n")

        scanner = RepositoryScanner(make_req(tmp_path, include=["*.py"]))
        _, scanned, _ = scanner.scan()
        assert scanned == 1

    def test_exclude_patterns(self, tmp_path):
        (tmp_path / "keep.py").write_text("x = 1\n")
        (tmp_path / "skip.js").write_text("x = 1;\n")

        scanner = RepositoryScanner(make_req(tmp_path, exclude=["*.js"]))
        _, scanned, _ = scanner.scan()
        assert scanned == 1
