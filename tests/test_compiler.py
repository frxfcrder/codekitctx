import json
from pathlib import Path

from codekitctx.compiler.json_fmt import render_json
from codekitctx.compiler.markdown import render_markdown
from codekitctx.compiler.prompt import SYSTEM_PROMPT_PREFIX, wrap_prompt
from codekitctx.models import FileEntry


def make_file(rel_path="src/main.py", content="x = 1", language="Python", loc=1):
    return FileEntry(
        path=Path(rel_path),
        relative_path=rel_path,
        size_bytes=len(content),
        language=language,
        loc=loc,
        content=content,
    )


class TestRenderMarkdown:
    def test_contains_file_section(self):
        out = render_markdown([make_file()], tree="", stats={})
        assert "## CODEBASE SOURCE FILES" in out

    def test_contains_file_tag(self):
        out = render_markdown([make_file()], tree="", stats={})
        assert '<file path="src/main.py">' in out
        assert "</file>" in out

    def test_contains_content(self):
        out = render_markdown([make_file(content="print('hi')")], tree="", stats={})
        assert "print('hi')" in out

    def test_stats_section_when_provided(self):
        stats = {"total_files": 5, "total_loc": 100, "languages": {"Python": 1.0}}
        out = render_markdown([make_file()], tree="", stats=stats)
        assert "## PROJECT STATS" in out
        assert "Total Files: 5" in out
        assert "Total LOC: 100" in out
        assert "Python: 100%" in out

    def test_no_stats_section_when_empty(self):
        out = render_markdown([make_file()], tree="", stats={})
        assert "## PROJECT STATS" not in out

    def test_tree_section_when_provided(self):
        out = render_markdown([make_file()], tree="```\n└── src\n```", stats={})
        assert "## PROJECT STRUCTURE" in out
        assert "└── src" in out

    def test_no_tree_section_when_empty(self):
        out = render_markdown([make_file()], tree="", stats={})
        assert "## PROJECT STRUCTURE" not in out

    def test_multiple_files(self):
        files = [make_file("a.py"), make_file("b.py")]
        out = render_markdown(files, tree="", stats={})
        assert out.count("<file") == 2

    def test_none_content_handled(self):
        f = make_file()
        f.content = None
        out = render_markdown([f], tree="", stats={})
        assert "</file>" in out


class TestRenderJson:
    def test_valid_json(self):
        out = render_json([make_file()], tree="", stats={}, warnings=[])
        data = json.loads(out)
        assert isinstance(data, dict)

    def test_top_level_keys(self):
        out = render_json([make_file()], tree="t", stats={}, warnings=["w"])
        data = json.loads(out)
        assert data["success"] is True
        assert data["tree"] == "t"
        assert data["warnings"] == ["w"]
        assert "stats" in data
        assert "files" in data

    def test_file_entries(self):
        out = render_json([make_file()], tree="", stats={}, warnings=[])
        data = json.loads(out)
        assert len(data["files"]) == 1
        f = data["files"][0]
        assert f["path"] == "src/main.py"
        assert f["language"] == "Python"
        assert f["loc"] == 1
        assert f["content"] == "x = 1"

    def test_stats_passed_through(self):
        stats = {"total_files": 3, "total_loc": 42}
        out = render_json([], tree="", stats=stats, warnings=[])
        data = json.loads(out)
        assert data["stats"] == stats

    def test_empty_files(self):
        out = render_json([], tree="", stats={}, warnings=[])
        data = json.loads(out)
        assert data["files"] == []


class TestWrapPrompt:
    def test_prepends_prefix(self):
        out = wrap_prompt("some content")
        assert out.startswith(SYSTEM_PROMPT_PREFIX)

    def test_contains_content(self):
        out = wrap_prompt("some content")
        assert "some content" in out

    def test_prefix_mentions_ai(self):
        assert "AI" in SYSTEM_PROMPT_PREFIX or "software engineer" in SYSTEM_PROMPT_PREFIX
