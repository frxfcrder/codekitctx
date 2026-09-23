import os

import pytest
from fastapi.testclient import TestClient

from codekitctx import server
from codekitctx.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv(server.ALLOWED_ROOTS_ENV, str(tmp_path))
    monkeypatch.delenv(server.API_KEY_ENV, raising=False)
    server.rate_limit_buckets.clear()
    return TestClient(app)


@pytest.fixture
def sample_repo(tmp_path):
    (tmp_path / "app.py").write_text("def main():\n    pass\n")
    (tmp_path / "README.md").write_text("# Test\n")
    return tmp_path


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestCompile:
    def test_compile_success(self, client, sample_repo):
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "tree": False, "stats": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["files_scanned"] == 2

    def test_compile_response_fields(self, client, sample_repo):
        resp = client.post("/compile", json={"repo_path": str(sample_repo)})
        data = resp.json()
        for key in [
            "success",
            "context",
            "stats",
            "tree",
            "files_scanned",
            "files_skipped",
            "skipped_breakdown",
            "warnings",
        ]:
            assert key in data

    def test_compile_json_format(self, client, sample_repo):
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "format": "json"},
        )
        data = resp.json()
        assert '"success"' in data["context"]

    def test_compile_with_files(self, client, sample_repo):
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "files": ["app.py"]},
        )
        data = resp.json()
        assert data["files_scanned"] == 1

    def test_compile_with_prompt(self, client, sample_repo):
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "prompt": True},
        )
        data = resp.json()
        assert "expert AI software engineer" in data["context"]

    def test_compile_invalid_path_returns_400(self, client):
        resp = client.post(
            "/compile",
            json={"repo_path": "/nonexistent/path/xyz"},
        )
        assert resp.status_code == 400

    def test_compile_compact(self, client, sample_repo):
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "compact": True},
        )
        data = resp.json()
        assert data["success"] is True


class TestCompileRaw:
    def test_raw_returns_text(self, client, sample_repo):
        resp = client.post(
            "/compile/raw",
            json={"repo_path": str(sample_repo), "tree": False, "stats": False},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert "## CODEBASE SOURCE FILES" in resp.text

    def test_raw_json_format(self, client, sample_repo):
        resp = client.post(
            "/compile/raw",
            json={"repo_path": str(sample_repo), "format": "json"},
        )
        assert resp.status_code == 200
        assert '"success"' in resp.text
