from pathlib import Path

from codekitctx.core.filters import FilterManager
from codekitctx.models import SkipReason


class TestEvaluate:
    def test_no_filters_includes_everything(self):
        fm = FilterManager()
        included, reason = fm.evaluate(Path("any/file.py"))
        assert included is True
        assert reason is None

    def test_exclude_match(self):
        fm = FilterManager(exclude=["*.test.ts"])
        included, reason = fm.evaluate(Path("app.test.ts"))
        assert included is False
        assert reason == SkipReason.IGNORED

    def test_exclude_no_match(self):
        fm = FilterManager(exclude=["*.test.ts"])
        included, reason = fm.evaluate(Path("app.ts"))
        assert included is True
        assert reason is None

    def test_include_match(self):
        fm = FilterManager(include=["*.py"])
        included, _ = fm.evaluate(Path("main.py"))
        assert included is True

    def test_include_no_match(self):
        fm = FilterManager(include=["*.py"])
        included, reason = fm.evaluate(Path("main.js"))
        assert included is False
        assert reason == SkipReason.IGNORED

    def test_exclude_takes_priority(self):
        fm = FilterManager(include=["*.py"], exclude=["conftest.py"])
        included, _ = fm.evaluate(Path("main.py"))
        assert included is True
        included, _ = fm.evaluate(Path("conftest.py"))
        assert included is False

    def test_directory_glob(self):
        fm = FilterManager(exclude=["node_modules/*"])
        included, _ = fm.evaluate(Path("node_modules/pkg/index.js"))
        assert included is False

    def test_nested_path(self):
        fm = FilterManager(include=["src/*"])
        included, _ = fm.evaluate(Path("src/app/main.py"))
        assert included is True


class TestShouldEvaluate:
    def test_returns_true_when_included(self):
        fm = FilterManager()
        assert fm.should_evaluate(Path("file.py")) is True

    def test_returns_false_when_excluded(self):
        fm = FilterManager(exclude=["*.log"])
        assert fm.should_evaluate(Path("debug.log")) is False

    def test_returns_false_when_not_included(self):
        fm = FilterManager(include=["*.py"])
        assert fm.should_evaluate(Path("style.css")) is False
