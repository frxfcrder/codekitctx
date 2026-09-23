import argparse
import sys
import io
from pathlib import Path

from codekitctx.core.context import RepoContext
from codekitctx.output.clipboard import copy_to_clipboard
from codekitctx.output.file import save_to_file

WELCOME_BANNER = r"""
 ██████╗ ██████╗ ██████╗ ███████╗██╗  ██╗██╗████████╗ ██████╗████████╗██╗  ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝██║ ██╔╝██║╚══██╔══╝██╔════╝╚══██╔══╝╚██╗██╔╝
██║     ██║   ██║██║  ██║█████╗  █████╔╝ ██║   ██║   ██║        ██║    ╚███╔╝ 
██║     ██║   ██║██║  ██║██╔══╝  ██╔═██╗ ██║   ██║   ██║        ██║    ██╔██╗ 
╚██████╗╚██████╔╝██████╔╝███████╗██║  ██╗██║   ██║   ╚██████╗   ██║   ██╔╝ ██╗
 ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝   ╚═╝    ╚═════╝   ╚═╝   ╚═╝  ╚═╝

        Codebase Context Compiler
        Turn repositories into AI-ready context.
"""

WELCOME_INFO = """
Welcome to CodeKitCtx! 🚀
Pack your entire codebase into a clean, structured context file for ChatGPT, Claude, Cursor, and v0.

Quick Examples:
  codekitctx .                       # Output codebase context to terminal
  codekitctx . -o context.md          # Save output to context.md
  codekitctx . --copy                # Copy context directly to system clipboard
  codekitctx . --compact             # Extract AST signatures & functions only
  codekitctx . --prompt -o ctx.md    # Prepend AI assistant instructions
  codekitctx --welcome               # Show this welcome screen

Options & Flags:
  --compact        Use tree-sitter AST parsing to minify code
  --prompt         Prepend AI system prompt wrapper
  --include        Filter specific file patterns (e.g. "*.py" "*.ts")
  --exclude        Exclude file patterns (e.g. "*.test.js")
  --format         Choose output format: 'markdown' or 'json'

Run 'codekitctx --help' for full parameter details.
=================================================
"""


def print_welcome_page():
    """Prints the ASCII logo and welcome guide."""
    print(WELCOME_BANNER, file=sys.stderr)
    print(WELCOME_INFO, file=sys.stderr)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="codekitctx",
        description="CodeKitCtx: Compile software repositories into structured LLM context.",
    )

    # Welcome / Info Flag
    parser.add_argument(
        "--welcome",
        action="store_true",
        help="Display the welcome page, ASCII logo, and quick start guide",
    )

    # Core Options
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=None,  # Set to None to detect when user passes no path
        help="Path to the repository root directory",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Path to save the generated output file (e.g., context.md)",
    )
    parser.add_argument(
        "-c",
        "--copy",
        action="store_true",
        help="Copy compiled output directly to system clipboard",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    # Feature Flags
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Enable AST compact mode (extracts class, function signatures & imports)",
    )
    parser.add_argument(
        "--prompt",
        action="store_true",
        help="Prepend AI assistant prompt instructions to output",
    )
    parser.add_argument(
        "--no-tree",
        action="store_false",
        dest="tree",
        help="Disable project directory tree in output",
    )
    parser.add_argument(
        "--no-stats",
        action="store_false",
        dest="stats",
        help="Disable project statistics in output",
    )

    # Filtering Options
    parser.add_argument(
        "--include",
        nargs="*",
        default=[],
        help="Include file patterns (e.g. '*.py' '*.ts')",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Exclude file patterns (e.g. '*.test.ts')",
    )
    parser.add_argument(
        "--max-size",
        type=int,
        default=1_048_576,
        help="Maximum file size limit in bytes (default: 1048576 / 1MB)",
    )
    parser.add_argument(
        "--allow-sensitive",
        action="store_true",
        help="Allow including sensitive files (like .env) if detected",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="Explicit file paths to include (relative to repo root)",
    )

    args = parser.parse_args()

    # 1. Show Welcome Page if requested explicitly OR if no path/arguments provided
    if args.welcome or (args.repo_path is None and len(sys.argv) == 1):
        print_welcome_page()
        sys.exit(0)

    # Fallback to current directory if default path wasn't provided
    target_repo_path = args.repo_path or "."

    # 2. Print ASCII header on standard compilation runs
    print(WELCOME_BANNER, file=sys.stderr)

    # Validate target directory
    target_path = Path(target_repo_path).resolve()
    if not target_path.exists() or not target_path.is_dir():
        print(f"Error: Repository path '{target_repo_path}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    print(f"Compiling repository context for: {target_path} ...\n", file=sys.stderr)

    # Invoke Orchestrator
    try:
        ctx = RepoContext(str(target_path))
        result = ctx.compile(
            tree=args.tree,
            stats=args.stats,
            prompt=args.prompt,
            compact=args.compact,
            format=args.format,
            include=args.include,
            exclude=args.exclude,
            max_size=args.max_size,
            files=args.files,
            allow_sensitive=args.allow_sensitive,
        )
    except Exception as e:
        print(f"Error compiling repository: {e}", file=sys.stderr)
        sys.exit(1)

    # Display Warnings
    for warning in result.warnings:
        print(f"⚠️  {warning}", file=sys.stderr)

    # Display Skip Summary
    if result.files_skipped > 0:
        breakdown_str = ", ".join(f"{k}: {v}" for k, v in result.skipped_breakdown.items())
        print(f"ℹ️  Skipped {result.files_skipped} file(s) ({breakdown_str})", file=sys.stderr)

    # Handle Clipboard Copy
    if args.copy:
        if copy_to_clipboard(result.markdown):
            print("✨ Context copied to system clipboard!", file=sys.stderr)
        else:
            print("❌ Clipboard copy failed. Ensure 'pyperclip' is installed.", file=sys.stderr)

    # Handle Output File Writing vs Terminal stdout
    if args.output:
        try:
            out_file = save_to_file(result.markdown, args.output)
            print(f"✅ Context saved to {out_file}", file=sys.stderr)
        except Exception as e:
            print(f"Error saving file '{args.output}': {e}", file=sys.stderr)
            sys.exit(1)
    elif not args.copy:
        sys.stdout.write(result.markdown)


if __name__ == "__main__":
    main()