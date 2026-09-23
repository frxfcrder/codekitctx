import pytest
from fastapi.testclient import TestClient

from codekitctx import server
from codekitctx.server import app


@pytest.fixture
def sample_repo(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    return tmp_path


def make_client(monkeypatch, tmp_path, api_key=None, extra_roots=""):
    monkeypatch.setenv(server.ALLOWED_ROOTS_ENV, str(tmp_path))
    if api_key is None:
        monkeypatch.delenv(server.API_KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(server.API_KEY_ENV, api_key)
    server.rate_limit_buckets.clear()
    return TestClient(app)


class TestPathValidation:
    def test_nonexistent_path_returns_400(self, monkeypatch, tmp_path):
        client = make_client(monkeypatch, tmp_path)
        resp = client.post("/compile", json={"repo_path": str(tmp_path / "nope")})
        assert resp.status_code == 400

    def test_file_not_dir_returns_400(self, monkeypatch, tmp_path):
        f = tmp_path / "file.py"
        f.write_text("x = 1\n")
        client = make_client(monkeypatch, tmp_path)
        resp = client.post("/compile", json={"repo_path": str(f)})
        assert resp.status_code == 400

    def test_outside_allowlist_returns_403(self, monkeypatch, tmp_path):
        client = make_client(monkeypatch, tmp_path)
        other = tmp_path.parent / "elsewhere_dir"
        other.mkdir(exist_ok=True)
        resp = client.post("/compile", json={"repo_path": str(other)})
        assert resp.status_code == 403

    def test_traversal_in_files_rejected(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path)
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "files": ["../../../etc/passwd"]},
        )
        assert resp.status_code in (400, 403)

    def test_absolute_escape_file_rejected(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path)
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "files": ["/etc/passwd"]},
        )
        assert resp.status_code in (400, 403)

    @pytest.mark.skipif(
        not hasattr(__import__("pathlib").Path, "symlink_to"),
        reason="symlinks unsupported on this platform",
    )
    def test_symlink_escape_rejected(self, monkeypatch, tmp_path, sample_repo):
        import os

        target = tmp_path / "secret_target"
        target.mkdir(exist_ok=True)
        (target / "secret.txt").write_text("secret")
        link_dir = sample_repo / "evil_link"
        try:
            link_dir.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("cannot create symlinks on this platform")

        client = make_client(monkeypatch, tmp_path)
        resp = client.post("/compile", json={"repo_path": str(sample_repo)})
        assert resp.status_code == 200
        assert "evil_link" not in resp.json()["context"]


class TestAuth:
    def test_no_key_allows_access(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path, api_key=None)
        resp = client.post("/compile", json={"repo_path": str(sample_repo)})
        assert resp.status_code == 200

    def test_key_required_when_set_missing_header_401(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path, api_key="secret123")
        resp = client.post("/compile", json={"repo_path": str(sample_repo)})
        assert resp.status_code == 401

    def test_wrong_key_403(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path, api_key="secret123")
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo)},
            headers={"X-API-Key": "wrong"},
        )
        assert resp.status_code == 403

    def test_correct_x_api_key_200(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path, api_key="secret123")
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo)},
            headers={"X-API-Key": "secret123"},
        )
        assert resp.status_code == 200

    def test_bearer_token_200(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path, api_key="secret123")
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo)},
            headers={"Authorization": "Bearer secret123"},
        )
        assert resp.status_code == 200

    def test_health_open_without_key(self, monkeypatch, tmp_path):
        client = make_client(monkeypatch, tmp_path, api_key="secret123")
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_wrong_key_on_raw_403(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path, api_key="secret123")
        resp = client.post(
            "/compile/raw",
            json={"repo_path": str(sample_repo)},
            headers={"X-API-Key": "bad"},
        )
        assert resp.status_code == 403


class TestRateLimit:
    def test_rate_limit_429(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path)
        body = {"repo_path": str(sample_repo), "tree": False, "stats": False}
        statuses = []
        for _ in range(server.RATE_LIMIT_MAX_REQUESTS + 2):
            resp = client.post("/compile", json=body)
            statuses.append(resp.status_code)
        assert 429 in statuses
        assert statuses[0] == 200

    def test_health_not_rate_limited(self, monkeypatch, tmp_path):
        client = make_client(monkeypatch, tmp_path)
        for _ in range(server.RATE_LIMIT_MAX_REQUESTS + 3):
            resp = client.get("/health")
            assert resp.status_code == 200


class TestRequestLimits:
    def test_oversized_body_413(self, monkeypatch, tmp_path):
        client = make_client(monkeypatch, tmp_path)
        big = "x" * (server.MAX_REQUEST_BODY_BYTES + 100)
        resp = client.post(
            "/compile",
            content=big,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 413


class TestPydanticValidation:
    def test_invalid_format_rejected(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path)
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "format": "xml"},
        )
        assert resp.status_code == 422

    def test_negative_max_size_rejected(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path)
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "max_size": -1},
        )
        assert resp.status_code == 422

    def test_oversized_max_size_rejected(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path)
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "max_size": 100_000_000},
        )
        assert resp.status_code == 422

    def test_too_many_files_rejected(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path)
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "files": [f"f{i}.py" for i in range(1001)]},
        )
        assert resp.status_code == 422


class TestSafeMode:
    def test_safe_mode_blocks_allow_sensitive(self, monkeypatch, tmp_path, sample_repo):
        (sample_repo / ".env").write_text("SECRET=abc\n")
        monkeypatch.setenv(server.SAFE_MODE_ENV, "1")
        client = make_client(monkeypatch, tmp_path)
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "allow_sensitive": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["files_skipped"] >= 1
        assert data["skipped_breakdown"].get("sensitive", 0) >= 1
        assert "SECRET=abc" not in data["context"]


class TestStartupSecurity:
    def test_refuses_non_loopback_without_key(self, monkeypatch):
        monkeypatch.setattr(server, "_host_from_uvicorn_lifespan", lambda: None)
        monkeypatch.setattr(server, "_host_from_argv", lambda argv=None: None)
        monkeypatch.setenv(server.BIND_HOST_ENV, "0.0.0.0")
        monkeypatch.delenv(server.API_KEY_ENV, raising=False)
        with pytest.raises(RuntimeError, match="Refusing to start"):
            server.enforce_startup_security()

    def test_allows_non_loopback_with_key(self, monkeypatch):
        monkeypatch.setattr(server, "_host_from_uvicorn_lifespan", lambda: None)
        monkeypatch.setattr(server, "_host_from_argv", lambda argv=None: None)
        monkeypatch.setenv(server.BIND_HOST_ENV, "0.0.0.0")
        monkeypatch.setenv(server.API_KEY_ENV, "somekey")
        server.enforce_startup_security()

    def test_allows_loopback_without_key(self, monkeypatch):
        monkeypatch.setattr(server, "_host_from_uvicorn_lifespan", lambda: None)
        monkeypatch.setattr(server, "_host_from_argv", lambda argv=None: None)
        monkeypatch.setenv(server.BIND_HOST_ENV, "127.0.0.1")
        monkeypatch.delenv(server.API_KEY_ENV, raising=False)
        server.enforce_startup_security()

    def test_loopback_range_127_is_loopback(self):
        assert server.is_loopback_address("127.0.0.2") is True
        assert server.is_loopback_address("127.255.255.254") is True
        assert server.is_loopback_address("::1") is True
        assert server.is_loopback_address("192.168.1.1") is False
        assert server.is_loopback_address("0.0.0.0") is False
        assert server.is_loopback_address("evil.example.com") is False

    def test_argv_host_flag_beats_env(self, monkeypatch):
        monkeypatch.delenv(server.BIND_HOST_ENV, raising=False)
        monkeypatch.delenv(server.API_KEY_ENV, raising=False)
        monkeypatch.setattr(server, "_host_from_uvicorn_lifespan", lambda: None)
        monkeypatch.setattr(
            server.sys, "argv", ["uvicorn", "codekitctx.server:app", "--host", "0.0.0.0"]
        )
        assert server.resolve_bind_host() == ("0.0.0.0", True)
        with pytest.raises(RuntimeError, match="Refusing to start"):
            server.enforce_startup_security()

    def test_argv_host_equals_form(self, monkeypatch):
        monkeypatch.delenv(server.BIND_HOST_ENV, raising=False)
        monkeypatch.setattr(server, "_host_from_uvicorn_lifespan", lambda: None)
        monkeypatch.setattr(
            server.sys, "argv", ["uvicorn", "codekitctx.server:app", "--host=0.0.0.0"]
        )
        assert server.resolve_bind_host()[0] == "0.0.0.0"

    def test_argv_loopback_flag_allows_no_key(self, monkeypatch):
        monkeypatch.delenv(server.BIND_HOST_ENV, raising=False)
        monkeypatch.delenv(server.API_KEY_ENV, raising=False)
        monkeypatch.setattr(server, "_host_from_uvicorn_lifespan", lambda: None)
        monkeypatch.setattr(
            server.sys, "argv", ["uvicorn", "codekitctx.server:app", "--host", "127.0.0.1"]
        )
        server.enforce_startup_security()

    def test_non_uvicorn_argv_ignored(self, monkeypatch):
        monkeypatch.setenv(server.BIND_HOST_ENV, "127.0.0.1")
        monkeypatch.setattr(server, "_host_from_uvicorn_lifespan", lambda: None)
        monkeypatch.setattr(server.sys, "argv", ["pytest", "--host", "0.0.0.0"])
        assert server.resolve_bind_host() == ("127.0.0.1", False)

    def test_fail_closed_when_lifespan_host_missing(self, monkeypatch):
        monkeypatch.delenv(server.API_KEY_ENV, raising=False)
        monkeypatch.setattr(server, "_host_from_uvicorn_lifespan", lambda: "")
        monkeypatch.setattr(server, "_host_from_argv", lambda argv=None: None)
        with pytest.raises(RuntimeError, match="Refusing to start"):
            server.enforce_startup_security()

    def test_lifespan_host_used_when_present(self, monkeypatch):
        monkeypatch.delenv(server.BIND_HOST_ENV, raising=False)
        monkeypatch.delenv(server.API_KEY_ENV, raising=False)
        monkeypatch.setattr(server, "_host_from_uvicorn_lifespan", lambda: "0.0.0.0")
        assert server.resolve_bind_host() == ("0.0.0.0", True)
        with pytest.raises(RuntimeError, match="Refusing to start"):
            server.enforce_startup_security()

    def test_env_fallback_when_not_under_uvicorn(self, monkeypatch):
        monkeypatch.setattr(server, "_host_from_uvicorn_lifespan", lambda: None)
        monkeypatch.setattr(server, "_host_from_argv", lambda argv=None: None)
        monkeypatch.setenv(server.BIND_HOST_ENV, "127.0.0.1")
        assert server.resolve_bind_host() == ("127.0.0.1", False)


class TestTrustedHost:
    def test_disallowed_host_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setenv(server.ALLOWED_HOSTS_ENV, "localhost,127.0.0.1")
        monkeypatch.delenv(server.API_KEY_ENV, raising=False)
        server.rate_limit_buckets.clear()
        client = TestClient(app, base_url="http://evil.example.com")
        resp = client.get("/health")
        assert resp.status_code == 400

    def test_allowed_host_accepted(self, monkeypatch, tmp_path):
        client = make_client(monkeypatch, tmp_path, api_key=None)
        resp = client.get("/health")
        assert resp.status_code == 200


class TestScanLimits:
    def test_max_files_truncates(self, monkeypatch, tmp_path, sample_repo):
        for i in range(5):
            (sample_repo / f"extra{i}.py").write_text("x = 1\n")
        client = make_client(monkeypatch, tmp_path)
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "max_files": 3, "tree": False, "stats": False},
        )
        data = resp.json()
        assert data["files_scanned"] + data["files_skipped"] <= 3

    def test_max_depth_limits_walk(self, monkeypatch, tmp_path, sample_repo):
        deep = sample_repo
        for d in range(10):
            deep = deep / f"d{d}"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("x = 1\n")
        client = make_client(monkeypatch, tmp_path)
        resp = client.post(
            "/compile",
            json={"repo_path": str(sample_repo), "max_depth": 3, "tree": False, "stats": False},
        )
        assert resp.status_code == 200
        assert "d9" not in resp.json()["context"]


class TestErrorHygiene:
    def test_500_does_not_leak_exception_detail(self, monkeypatch, tmp_path, sample_repo):
        client = make_client(monkeypatch, tmp_path)

        def boom(*a, **k):
            raise ValueError("internal secret path /home/user/.ssh/id_rsa")

        monkeypatch.setattr(server, "RepoContext", lambda *a, **k: type("X", (), {"compile": staticmethod(boom)})())
        resp = client.post("/compile", json={"repo_path": str(sample_repo)})
        assert resp.status_code == 500
        assert "id_rsa" not in resp.text
        assert "secret" not in resp.text
