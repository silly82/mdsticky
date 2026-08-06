"""Platform-independent foundation for mdsticky."""

from __future__ import annotations

import argparse
import difflib
from dataclasses import dataclass
from pathlib import Path

CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


def base_path_for(path: str | Path) -> Path:
    """Return the synchronized base-snapshot path for a Markdown file."""
    path = Path(path)
    return path.with_name(path.name + ".mdsticky-base")


def load_text(path: str | Path) -> str:
    """Read UTF-8 text, returning an empty string only for a missing file."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write_text(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".mdsticky.tmp")
    temporary.write_text(text, encoding="utf-8", newline="")
    temporary.replace(path)


def write_base_snapshot(path: str | Path, text: str) -> None:
    """Atomically update the synchronized base snapshot for *path*."""
    _write_text(base_path_for(path), text)


def save_with_merge(path: str | Path, base: str, local: str) -> MergeResult:
    """Save *local* against the shared base, merging a newer external file.

    A conflicted result is written to the Markdown file but never promoted to
    the base snapshot. The next save therefore still has the original base.
    """
    path = Path(path)
    external = load_text(path)
    result = three_way_merge(base, local, external)
    _write_text(path, result.text)
    if not result.has_conflicts:
        write_base_snapshot(path, result.text)
    return result


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
    state = 0
    for line in text.splitlines():
        if state == 0 and line.startswith("<<<<<<< "):
            state = 1
        elif state == 1 and line == "=======":
            state = 2
        elif state == 2 and line.startswith(">>>>>>> "):
            return True
    return False


def _changes(base: list[str], other: list[str]) -> list[tuple[int, int, list[str]]]:
    matcher = difflib.SequenceMatcher(a=base, b=other, autojunk=False)
    return [
        (start, end, other[new_start:new_end])
        for tag, start, end, new_start, new_end in matcher.get_opcodes()
        if tag != "equal"
    ]


def _overlaps(left: tuple[int, int, list[str]], right: tuple[int, int, list[str]]) -> bool:
    ls, le, _ = left
    rs, re, _ = right
    # Treat insertions at a replacement boundary as overlapping. This is
    # deliberately conservative: losing either user's edit is worse than a
    # manual conflict.
    if le == ls and re == rs:
        return ls == rs
    if le == ls:
        return rs <= ls <= re
    if re == rs:
        return ls <= rs <= le
    return max(ls, rs) < min(le, re)


def _overlap_group(
    local_changes: list[tuple[int, int, list[str]]],
    external_changes: list[tuple[int, int, list[str]]],
) -> list[tuple[int, int, list[str], list[str]]]:
    pairs = [
        (local, external)
        for local in local_changes
        for external in external_changes
        if _overlaps(local, external) and local[2] != external[2]
    ]
    groups: list[list[tuple[int, int, list[str], list[str]]]] = []
    for local, external in pairs:
        item = (min(local[0], external[0]), max(local[1], external[1]), local[2], external[2])
        merged = [item]
        remaining: list[list[tuple[int, int, list[str], list[str]]]] = []
        for group in groups:
            if any(max(item[0], other[0]) <= min(item[1], other[1]) for other in group):
                merged.extend(group)
            else:
                remaining.append(group)
        remaining.append(merged)
        groups = remaining

    result = []
    for group in groups:
        start = min(item[0] for item in group)
        end = max(item[1] for item in group)
        result.append((start, end))
    return sorted(result, key=lambda item: item[0])


def _side_region(
    base_lines: list[str],
    changes: list[tuple[int, int, list[str]]],
    start: int,
    end: int,
) -> list[str]:
    output: list[str] = []
    cursor = start
    for change_start, change_end, replacement in sorted(changes, key=lambda item: item[0]):
        if change_end < start or change_start > end:
            continue
        change_start = max(change_start, start)
        change_end = min(change_end, end)
        output.extend(base_lines[cursor:change_start])
        output.extend(replacement)
        cursor = change_end
    output.extend(base_lines[cursor:end])
    return output


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
    conflicts = _overlap_group(local_changes, external_changes)

    if conflicts:
        output: list[str] = []
        cursor = 0
        for start, end in conflicts:
            output.extend(base_lines[cursor:start])
            output.append("<<<<<<< LOCAL\n")
            output.extend(_side_region(base_lines, local_changes, start, end))
            output.append("=======\n")
            output.extend(_side_region(base_lines, external_changes, start, end))
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
    parser = argparse.ArgumentParser(description="mdsticky core utilities")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("folder", nargs="?", help="folder to scan")
    args = parser.parse_args()
    if args.folder:
        for path in scan_markdown_files(args.folder):
            print(path)
    return 0


__all__ = [
    "base_path_for",
    "CONFLICT_MARKERS",
    "MergeResult",
    "contains_conflict_markers",
    "load_text",
    "scan_markdown_files",
    "save_with_merge",
    "write_base_snapshot",
    "three_way_merge",
    "unified_diff",
]

__version__ = "0.0.2"


if __name__ == "__main__":
    raise SystemExit(main())


def _version_for_argparse() -> str:
    return __version__


# argparse resolves this global at runtime after module initialization.
main.__annotations__ = {"return": int}
