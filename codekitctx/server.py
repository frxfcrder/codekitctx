import ipaddress
import logging
import os
import secrets
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from codekitctx.core.context import RepoContext
from codekitctx.models import ContextRequest, ContextResponse

logger = logging.getLogger("codekitctx")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

API_KEY_ENV = "CODEKITCTX_API_KEY"
ALLOWED_ROOTS_ENV = "CODEKITCTX_ALLOWED_ROOTS"
CORS_ORIGINS_ENV = "CODEKITCTX_CORS_ORIGINS"
SAFE_MODE_ENV = "CODEKITCTX_SAFE_MODE"
ALLOWED_HOSTS_ENV = "CODEKITCTX_ALLOWED_HOSTS"
BIND_HOST_ENV = "UVICORN_HOST"

MAX_REQUEST_BODY_BYTES = 1_000_000
MAX_RESPONSE_BODY_BYTES = 10_000_000
RATE_LIMIT_MAX_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60.0

rate_limit_buckets: dict[str, tuple[int, float]] = {}


def get_api_key() -> Optional[str]:
    return os.environ.get(API_KEY_ENV) or None


def get_allowed_repo_roots() -> List[Path]:
    raw_value = os.environ.get(ALLOWED_ROOTS_ENV, "")
    roots = [Path(part.strip()).resolve() for part in raw_value.split(";") if part.strip()]
    if not roots:
        roots = [Path.cwd().resolve()]
    return roots


def is_safe_mode_enabled() -> bool:
    return os.environ.get(SAFE_MODE_ENV, "1").lower() not in ("0", "false", "no")


def is_loopback_address(host: Optional[str]) -> bool:
    if host is None:
        return True
    host = host.strip()
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def redact_sensitive_path(path_str: str) -> str:
    file_name = Path(path_str).name
    if file_name.startswith(".") or any(
        marker in file_name.lower() for marker in ("secret", "credential", "key", "password")
    ):
        return f"<redacted:{file_name[:4]}...>"
    return path_str


def _host_from_uvicorn_lifespan() -> Optional[str]:
    try:
        from uvicorn.lifespan.on import LifespanOn
    except ImportError:
        return None
    frame = sys._getframe(1)
    while frame is not None:
        frame_self = frame.f_locals.get("self")
        if isinstance(frame_self, LifespanOn):
            host = getattr(frame_self.config, "host", None)
            return str(host) if host else ""
        frame = frame.f_back
    return None


def _host_from_argv(argv: Optional[List[str]] = None) -> Optional[str]:
    if argv is None:
        argv = sys.argv
    if not argv:
        return None
    argv0 = os.path.basename(argv[0]).lower()
    if not (argv0.startswith("uvicorn") or argv0 in ("uvicorn.exe", "__main__.py")):
        return None
    for i, arg in enumerate(argv[1:], start=1):
        if arg == "--host" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--host="):
            value = arg.split("=", 1)[1]
            if value:
                return value
    return None


def resolve_bind_host() -> Tuple[str, bool]:
    lifespan_host = _host_from_uvicorn_lifespan()
    if lifespan_host is not None:
        return lifespan_host, True
    argv_host = _host_from_argv()
    if argv_host is not None:
        return argv_host, True
    env_host = os.environ.get(BIND_HOST_ENV, "127.0.0.1")
    return env_host, False


def enforce_startup_security() -> None:
    bind_host, under_uvicorn = resolve_bind_host()
    api_key = get_api_key()

    if under_uvicorn and not bind_host:
        bind_host = ""

    if not is_loopback_address(bind_host) and not api_key:
        raise RuntimeError(
            f"Refusing to start: bound to non-loopback host '{bind_host or 'unknown'}' without "
            f"{API_KEY_ENV}. Set an API key or bind to 127.0.0.1."
        )

    if not api_key:
        logger.warning(
            "No API key set — unauthenticated access allowed on localhost only. "
            "Set %s before exposing this service.",
            API_KEY_ENV,
        )


def validate_repo_path(repo_path: str) -> Path:
    candidate = Path(repo_path).expanduser()
    try:
        resolved_path = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=400, detail=f"Repository path does not exist: {repo_path}")

    if not resolved_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Repository path is not a directory: {repo_path}")

    allowed_roots = get_allowed_repo_roots()
    if not any(resolved_path.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(
            status_code=403,
            detail="Repository path is outside the allowed roots (CODEKITCTX_ALLOWED_ROOTS)",
        )
    return resolved_path


def validate_files_within(repo_root: Path, files: List[str]) -> None:
    for relative_file in files:
        try:
            resolved_file = (repo_root / relative_file).resolve(strict=True)
        except (OSError, RuntimeError):
            raise HTTPException(status_code=400, detail=f"Requested file does not exist: {relative_file}")
        if not resolved_file.is_relative_to(repo_root):
            raise HTTPException(
                status_code=403,
                detail=f"Requested file escapes repository root: {relative_file}",
            )


def enforce_rate_limit(client_ip: str) -> None:
    current_time = time.monotonic()
    bucket = rate_limit_buckets.get(client_ip)

    if bucket is None or current_time - bucket[1] > RATE_LIMIT_WINDOW_SECONDS:
        rate_limit_buckets[client_ip] = (1, current_time)
        return

    request_count, window_start = bucket
    if request_count >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Rate limit exceeded, try again later")
    rate_limit_buckets[client_ip] = (request_count + 1, window_start)


async def verify_api_key(request: Request) -> None:
    configured_key = get_api_key()
    if configured_key is None:
        return

    provided_key = request.headers.get("X-API-Key")
    if not provided_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            provided_key = auth_header[len("Bearer "):]

    if not provided_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    if not secrets.compare_digest(provided_key.encode("utf-8"), configured_key.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid API key")


async def enforce_route_rate_limit(request: Request) -> None:
    client_ip = get_client_ip(request)
    enforce_rate_limit(client_ip)


async def compile_security_guards(
    request: Request,
    __: None = Depends(verify_api_key),
    ___: None = Depends(enforce_route_rate_limit),
) -> Request:
    return request


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_REQUEST_BODY_BYTES:
                    return PlainTextResponse("Request body too large", status_code=413)
            except ValueError:
                return PlainTextResponse("Invalid Content-Length", status_code=400)
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        start_time = time.monotonic()
        client_ip = get_client_ip(request)
        response = await call_next(request)
        duration_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "ip=%s method=%s path=%s status=%d duration_ms=%.1f",
            client_ip,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        enforce_startup_security()
        yield

    application = FastAPI(
        title="codekitctx",
        description="Codebase Context Compiler API",
        version="0.1.0",
        lifespan=lifespan,
    )

    cors_origins_raw = os.environ.get(
        CORS_ORIGINS_ENV, "http://localhost:5173,http://127.0.0.1:5173"
    )
    cors_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]
    if "*" in cors_origins:
        logger.warning("CORS wildcard origin detected — restricting to localhost defaults")
        cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

    allowed_hosts_raw = os.environ.get(
        ALLOWED_HOSTS_ENV, "localhost,127.0.0.1,testserver"
    )
    allowed_hosts = [host.strip() for host in allowed_hosts_raw.split(",") if host.strip()]

    application.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "Authorization"],
    )
    application.add_middleware(RequestSizeLimitMiddleware)
    application.add_middleware(RequestLoggingMiddleware)

    @application.get("/health")
    def health():
        return {"status": "ok"}

    def run_compile_safely(req: ContextRequest, request: Request):
        client_ip = get_client_ip(request)
        start_time = time.monotonic()

        repo_root = validate_repo_path(req.repo_path)
        validate_files_within(repo_root, req.files)

        if is_safe_mode_enabled():
            req = req.model_copy(update={"allow_sensitive": False})

        logger.info(
            "compile ip=%s repo=%s files_req=%d safe_mode=%s",
            client_ip,
            redact_sensitive_path(str(repo_root)),
            len(req.files),
            is_safe_mode_enabled(),
        )

        try:
            ctx = RepoContext(str(repo_root))
            result = ctx.compile(
                tree=req.tree,
                stats=req.stats,
                prompt=req.prompt,
                compact=req.compact,
                format=req.format,
                include=req.include,
                exclude=req.exclude,
                max_size=req.max_size,
                files=req.files,
                allow_sensitive=req.allow_sensitive,
                max_files=req.max_files,
                max_total_size=req.max_total_size,
                max_depth=req.max_depth,
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception(
                "compile failed for repo=%s", redact_sensitive_path(str(repo_root))
            )
            raise HTTPException(status_code=500, detail="Internal error compiling repository")

        response_size = len(result.markdown.encode("utf-8"))
        if response_size > MAX_RESPONSE_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Compiled output exceeds size limit")

        duration_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "compile done ip=%s scanned=%d skipped=%d duration_ms=%.1f",
            client_ip,
            result.files_scanned,
            result.files_skipped,
            duration_ms,
        )
        return result

    @application.post("/compile", dependencies=[Depends(compile_security_guards)])
    async def compile_repo(req: ContextRequest, request: Request):
        result = run_compile_safely(req, request)
        return ContextResponse(
            success=result.success,
            context=result.markdown,
            stats=result.stats,
            tree=result.tree,
            files_scanned=result.files_scanned,
            files_skipped=result.files_skipped,
            skipped_breakdown=result.skipped_breakdown,
            warnings=result.warnings,
        )

    @application.post(
        "/compile/raw",
        response_class=PlainTextResponse,
        dependencies=[Depends(compile_security_guards)],
    )
    async def compile_raw(req: ContextRequest, request: Request):
        result = run_compile_safely(req, request)
        return result.markdown

    return application


app = create_app()
