from codekitctx.core.stats import StatsCalculator
from codekitctx.models import FileEntry
from pathlib import Path


def make_file(rel_path, loc, language="Python"):
    return FileEntry(
        path=Path(rel_path),
        relative_path=rel_path,
        size_bytes=loc * 40,
        language=language,
        loc=loc,
        content="x\n" * loc,
    )


class TestStatsCalculator:
    def test_empty_input(self):
        stats = StatsCalculator.calculate([])
        assert stats["total_files"] == 0
        assert stats["total_loc"] == 0
        assert stats["languages"] == {}
        assert stats["largest_files"] == []

    def test_total_files(self):
        files = [make_file("a.py", 10), make_file("b.py", 20)]
        stats = StatsCalculator.calculate(files)
        assert stats["total_files"] == 2

    def test_total_loc(self):
        files = [make_file("a.py", 10), make_file("b.py", 20)]
        stats = StatsCalculator.calculate(files)
        assert stats["total_loc"] == 30

    def test_single_language_percentage(self):
        files = [make_file("a.py", 100)]
        stats = StatsCalculator.calculate(files)
        assert stats["languages"]["Python"] == 1.0

    def test_multiple_languages(self):
        files = [
            make_file("a.py", 75, "Python"),
            make_file("b.js", 25, "JavaScript"),
        ]
        stats = StatsCalculator.calculate(files)
        assert stats["languages"]["Python"] == 0.75
        assert stats["languages"]["JavaScript"] == 0.25

    def test_largest_files_sorted(self):
        files = [
            make_file("small.py", 5),
            make_file("large.py", 100),
            make_file("medium.py", 50),
        ]
        stats = StatsCalculator.calculate(files)
        paths = [f["path"] for f in stats["largest_files"]]
        assert paths == ["large.py", "medium.py", "small.py"]

    def test_largest_files_capped_at_5(self):
        files = [make_file(f"f{i}.py", i) for i in range(1, 10)]
        stats = StatsCalculator.calculate(files)
        assert len(stats["largest_files"]) == 5

    def test_largest_files_fields(self):
        files = [make_file("a.py", 10)]
        stats = StatsCalculator.calculate(files)
        lf = stats["largest_files"][0]
        assert lf["path"] == "a.py"
        assert lf["loc"] == 10

    def test_zero_loc_no_division_error(self):
        files = [make_file("empty.py", 0)]
        stats = StatsCalculator.calculate(files)
        assert stats["languages"]["Python"] == 0.0
