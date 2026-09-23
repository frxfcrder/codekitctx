# Change tracking

## Fix #1 — Detect real uvicorn bind host at startup

- [x] `resolve_bind_host()`: LifespanOn.config → argv `--host` → `UVICORN_HOST` → `127.0.0.1`
- [x] Fail-closed if uvicorn lifespan present but host empty (treated as non-loopback)
- [x] Tests: argv `--host 0.0.0.0` without env refuses; equals-form; non-uvicorn argv ignored; lifespan host preferred; fail-closed; existing env tests unchanged
- [x] README / `.env.example` notes
- [x] pytest green

### Notes
- Precedence matches uvicorn: CLI flag > `UVICORN_HOST` env > default `127.0.0.1`
- No new dependencies; stack-walk is try/except-safe on uvicorn internals
- `TestClient` (pytest) has no `LifespanOn` frame → env fallback keeps existing tests green
