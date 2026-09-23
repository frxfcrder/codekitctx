from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class SkipReason(str, Enum):
    SENSITIVE = "sensitive"
    IGNORED = "ignored"
    MAX_SIZE = "max_size"
    UNREADABLE = "unreadable"
    TOO_LARGE = "too_large"
    BINARY = "binary"
    UNSUPPORTED = "unsupported"
    READ_ERROR = "read_error"


class ContextRequest(BaseModel):
    repo_path: str = Field(default=".", description="Path to the repository")
    github_url: Optional[str] = Field(default=None, description="Remote GitHub repository URL")
    tree: bool = True
    stats: bool = True
    prompt: bool = False
    compact: bool = False
    format: str = "markdown"  # "markdown" or "json"
    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)
    max_size: int = 1_048_576  # 1 MB
    files: List[str] = Field(default_factory=list)
    allow_sensitive: bool = False


class FileEntry(BaseModel):
    path: Path
    relative_path: str
    size_bytes: int
    language: str
    loc: int
    content: Optional[str] = None
    
    is_skipped: bool = False
    skip_reason: Optional[SkipReason] = None


class ContextResult(BaseModel):
    success: bool = True
    markdown: str = ""
    stats: Dict = Field(default_factory=dict)
    tree: str = ""
    files_scanned: int = 0
    files_skipped: int = 0
    skipped_breakdown: Dict = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class ContextResponse(BaseModel):
    success: bool
    context: str
    stats: Dict
    tree: str
    files_scanned: int
    files_skipped: int
    skipped_breakdown: Dict = Field(default_factory=dict)
    warnings: List[str]
