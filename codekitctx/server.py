from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse

from codekitctx.core.context import RepoContext
from codekitctx.models import ContextRequest, ContextResponse

app = FastAPI(
    title="codekitctx",
    description="Codebase Context Compiler API",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/compile")
def compile_repo(req: ContextRequest):
    try:
        ctx = RepoContext(req.repo_path)
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
        )
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compile/raw", response_class=PlainTextResponse)
def compile_raw(req: ContextRequest):
    try:
        ctx = RepoContext(req.repo_path)
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
        )
        return result.markdown
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
