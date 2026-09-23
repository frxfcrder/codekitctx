"""Basic library usage example."""

from codekitctx import RepoContext


def main():
    # Compile current directory to markdown
    ctx = RepoContext(".")
    result = ctx.compile(format="markdown")

    print(f"Files scanned: {result.files_scanned}")
    print(f"Files skipped: {result.files_skipped}")
    print(f"Total LOC: {result.stats.get('total_loc', 0)}")
    print(f"\nLanguages: {result.stats.get('languages', {})}")
    print(f"\nFirst 500 chars of output:\n{result.markdown[:500]}")


def compact_json_example():
    # Compact mode: AST signatures instead of full source
    ctx = RepoContext(".")
    result = ctx.compile(compact=True, format="json")

    print(f"\nCompact JSON output:\n{result.markdown[:500]}")


def filtered_example():
    # Only include Python files, exclude tests
    ctx = RepoContext(".")
    result = ctx.compile(
        include=["*.py"],
        exclude=["test_*"],
        tree=True,
        stats=True,
    )

    print(f"\nFiltered: {result.files_scanned} files")
    print(f"Tree:\n{result.tree}")


if __name__ == "__main__":
    main()
    compact_json_example()
    filtered_example()
