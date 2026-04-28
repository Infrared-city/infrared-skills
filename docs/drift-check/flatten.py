"""Flatten a git repo into a single Markdown blob with path-encoded headings.

Used by the drift-check Windmill flow to render an entire repo as one document
the LLM can navigate. Every file becomes a section whose heading is its
repo-relative path; depth = path depth + 2 (so root files are H2).

Usage::

    python flatten.py <repo_path> <label> [<commit_sha>]
"""
from __future__ import annotations

import sys
from pathlib import Path

INCLUDE_SUFFIXES = {".md", ".mdc", ".py", ".json", ".yaml", ".yml", ".toml"}
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".ruff_cache", "dist", "build", "outputs",
}
EXCLUDE_FILES = {
    "poetry.lock", "uv.lock", "package-lock.json", "pnpm-lock.yaml",
    ".env", ".coverage",
}
MAX_DEPTH = 6  # cap heading depth so we don't emit H7+ which Markdown ignores


def flatten(root: Path, label: str, commit: str = "?") -> str:
    out: list[str] = [f"# {label}\n\n_snapshot @ {commit}_\n"]
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in INCLUDE_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if rel.name in EXCLUDE_FILES:
            continue
        rel_str = rel.as_posix()
        depth = min(rel_str.count("/") + 2, MAX_DEPTH)
        body = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".md":
            out.append(f"\n{'#' * depth} {rel_str}\n\n{body}")
        else:
            lang = path.suffix.lstrip(".")
            out.append(f"\n{'#' * depth} {rel_str}\n\n```{lang}\n{body}\n```")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.stderr.write("usage: flatten.py <repo_path> <label> [<commit>]\n")
        sys.exit(2)
    repo = Path(sys.argv[1]).expanduser().resolve()
    label = sys.argv[2]
    commit = sys.argv[3] if len(sys.argv) > 3 else "?"
    sys.stdout.write(flatten(repo, label, commit))
