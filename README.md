# codekitctx

Codebase Context Compiler as a Python Library & FastAPI Service.
Turn your codebase into AI-ready context.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e ".[dev]"
```

## Run

```bash
uvicorn repoctx.server:app --reload
```

## Test

```bash
pytest
```
