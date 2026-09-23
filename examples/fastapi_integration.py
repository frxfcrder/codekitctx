"""FastAPI integration example.

Run the server first:
    uvicorn codekitctx.server:app --reload

Then run this script:
    python examples/fastapi_integration.py
"""

import httpx

BASE_URL = "http://127.0.0.1:8000"


def health_check():
    resp = httpx.get(f"{BASE_URL}/health")
    print(f"Health: {resp.json()}")


def compile_repo():
    payload = {
        "repo_path": ".",
        "tree": True,
        "stats": True,
        "format": "markdown",
        "prompt": False,
        "compact": False,
    }
    resp = httpx.post(f"{BASE_URL}/compile", json=payload, timeout=30.0)
    data = resp.json()

    print(f"Success: {data['success']}")
    print(f"Files scanned: {data['files_scanned']}")
    print(f"Files skipped: {data['files_skipped']}")
    if data["warnings"]:
        print(f"Warnings: {data['warnings']}")
    print(f"\nContext preview:\n{data['context'][:500]}")


def compile_raw():
    payload = {"repo_path": ".", "format": "json", "compact": True}
    resp = httpx.post(f"{BASE_URL}/compile/raw", json=payload, timeout=30.0)
    print(f"\nRaw JSON output:\n{resp.text[:500]}")


if __name__ == "__main__":
    try:
        health_check()
        compile_repo()
        compile_raw()
    except httpx.ConnectError:
        print("Server not running. Start it with:")
        print("  uvicorn codekitctx.server:app --reload")
