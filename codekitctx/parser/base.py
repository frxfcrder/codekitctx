from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Protocol


@dataclass
class Symbol:
    name: str
    kind: str
    line_start: int
    line_end: int
    signature: str = ""
    parent: Optional[str] = None
    children: List["Symbol"] = field(default_factory=list)


class BaseParser(Protocol):
    def parse(self, content: str, path: Path) -> List[Symbol]: ...
