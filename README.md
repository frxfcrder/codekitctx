# CodeKitCtx

Codebase Context Compiler — turn repositories into AI-ready context.

Scans a codebase, computes stats and a file tree, extracts symbols via tree-sitter, and compiles everything into Markdown or JSON for LLM prompts.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e .
```

## CLI Usage

### Generate repository context

```bash
codekitctx .                          # Output full context to terminal
codekitctx . -o context.md            # Save to file
codekitctx . --copy                   # Copy to clipboard
```

### Generate compact context

Extracts class/function signatures instead of full file contents — great for large repos.

```bash
codekitctx . --compact
codekitctx . --compact -f json -o context.json
```

### Filter files

```bash
codekitctx . --include "*.py" "*.ts"          # Only Python and TypeScript
codekitctx . --exclude "*.test.ts" "*.spec.*" # Skip test files
codekitctx . --files src/main.py src/api.py   # Explicit files only
```

### Options

| Flag | Description |
|---|---|
| `-o, --output PATH` | Save output to a file |
| `-c, --copy` | Copy output to clipboard |
| `-f, --format` | `markdown` (default) or `json` |
| `--compact` | AST signatures instead of full source |
| `--prompt` | Prepend AI system prompt wrapper |
| `--no-tree` | Exclude directory tree |
| `--no-stats` | Exclude file statistics |
| `--include PATTERNS` | Glob patterns to include |
| `--exclude PATTERNS` | Glob patterns to exclude |
| `--files PATHS` | Explicit file paths to include |
| `--max-size BYTES` | Max file size (default 1 MB) |
| `--allow-sensitive` | Include files flagged as sensitive |
| `--welcome` | Show welcome screen |

## API Usage

```bash
uvicorn codekitctx.server:app --reload
```

### POST `/compile`

Returns structured JSON response.

```json
{
  "repo_path": ".",
  "tree": true,
  "stats": true,
  "compact": false,
  "format": "markdown",
  "prompt": false
}
```

### POST `/compile/raw`

Returns the compiled context as plain text.

### GET `/health`

```json
{ "status": "ok" }
```

## Library Usage

```python
from codekitctx import RepoContext

ctx = RepoContext("./my-repo")
result = ctx.compile(format="markdown", compact=True)

print(result.markdown)      # Compiled output
print(result.stats)         # {total_files, total_loc, languages, ...}
print(result.tree)          # Directory tree
print(result.warnings)      # Any warnings during scan
```

### Async

```python
from codekitctx import AsyncRepoContext

ctx = AsyncRepoContext("./my-repo")
result = await ctx.compile_async()
```

## Supported Languages

Python, TypeScript, JavaScript, Rust, Go, Java, C, C++, C#, Ruby

## Development

```bash
pip install -e ".[dev]"   # Install with test dependencies
pytest                     # Run tests
```