"""Platform-independent foundation for mdsticky."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


@dataclass(frozen=True)
class MergeResult:
    text: str
    has_conflicts: bool


def scan_markdown_files(root: str | Path) -> list[Path]:
    """Return every Markdown document below *root*, excluding mdsticky bases."""
    root = Path(root)
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".md", ".markdown"}
            and not path.name.endswith(".mdsticky-base")
            and ".sync-conflict-" not in path.name
        ),
        key=lambda path: path.as_posix().lower(),
    )


def contains_conflict_markers(text: str) -> bool:
    return any(line.startswith(marker) for line in text.splitlines() for marker in CONFLICT_MARKERS)


def _changes(base: list[str], other: list[str]) -> list[tuple[int, int, list[str]]]:
    matcher = difflib.SequenceMatcher(a=base, b=other, autojunk=False)
    return [
        (start, end, other[new_start:new_end])
        for tag, start, end, new_start, new_end in matcher.get_opcodes()
        if tag != "equal"
    ]


def three_way_merge(base: str, local: str, external: str) -> MergeResult:
    """Merge independent line changes and mark overlapping changes."""
    if local == external:
        return MergeResult(local, False)
    if local == base:
        return MergeResult(external, False)
    if external == base:
        return MergeResult(local, False)

    base_lines = base.splitlines(keepends=True)
    local_lines = local.splitlines(keepends=True)
    external_lines = external.splitlines(keepends=True)
    local_changes = _changes(base_lines, local_lines)
    external_changes = _changes(base_lines, external_lines)

    conflicts: list[tuple[int, int, list[str], list[str]]] = []
    for ls, le, lnew in local_changes:
        for es, ee, enew in external_changes:
            if max(ls, es) < min(le, ee) or (ls == le == es == ee):
                if lnew != enew:
                    conflicts.append((min(ls, es), max(le, ee), lnew, enew))

    if conflicts:
        output: list[str] = []
        cursor = 0
        for start, end, lnew, enew in conflicts:
            output.extend(base_lines[cursor:start])
            output.append("<<<<<<< LOCAL\n")
            output.extend(lnew)
            output.append("=======\n")
            output.extend(enew)
            output.append(">>>>>>> EXTERNAL\n")
            cursor = end
        output.extend(base_lines[cursor:])
        return MergeResult("".join(output), True)

    combined = list(base_lines)
    all_changes = [(start, end, new) for start, end, new in local_changes]
    all_changes += [(start, end, new) for start, end, new in external_changes]
    for start, end, new in sorted(all_changes, key=lambda item: item[0], reverse=True):
        combined[start:end] = new
    return MergeResult("".join(combined), False)


def unified_diff(original: str, current: str, original_name: str = "original", current_name: str = "current") -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile=original_name,
            tofile=current_name,
        )
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="mdsticky core utilities")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("folder", nargs="?", help="folder to scan")
    args = parser.parse_args()
    if args.folder:
        for path in scan_markdown_files(args.folder):
            print(path)
    return 0


__all__ = [
    "CONFLICT_MARKERS",
    "MergeResult",
    "contains_conflict_markers",
    "scan_markdown_files",
    "three_way_merge",
    "unified_diff",
]

__version__ = "0.0.1"


if __name__ == "__main__":
    raise SystemExit(main())
