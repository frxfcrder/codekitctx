SYSTEM_PROMPT_PREFIX = """You are an expert AI software engineer analyzing this codebase.
Use the repository structure, statistics, and source files below to answer questions or fulfill implementation requests.
---
"""


def wrap_prompt(content: str) -> str:
    """Prepends AI instruction headers to compiled context."""
    return f"{SYSTEM_PROMPT_PREFIX}\n{content}"