#!/usr/bin/env python3
"""Synchronize the docs system instruction set into another repository.

The script compares semantic versions stored in the frontmatter of
`DOCS_SYSTEM_INSTRUCTION_SET.md` before copying so downstream repositories can
decide whether an upgrade is required.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TARGET = Path("docs/DOCS_SYSTEM_INSTRUCTION_SET.md")


class SyncError(RuntimeError):
    """Raised when synchronization cannot proceed safely."""


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, raw: str) -> "SemVer":
        parts = raw.strip().split(".")
        if len(parts) != 3:
            raise SyncError(f"Expected semantic version (MAJOR.MINOR.PATCH), got '{raw}'.")
        try:
            major, minor, patch = (int(part) for part in parts)
        except ValueError as exc:  # pragma: no cover - value error detail is enough
            raise SyncError(f"Version components must be integers, got '{raw}'.") from exc
        return cls(major, minor, patch)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def compare(self, other: "SemVer") -> int:
        if (cmp := (self.major - other.major)) != 0:
            return 1 if cmp > 0 else -1
        if (cmp := (self.minor - other.minor)) != 0:
            return 1 if cmp > 0 else -1
        if (cmp := (self.patch - other.patch)) != 0:
            return 1 if cmp > 0 else -1
        return 0


def read_frontmatter_version(path: Path) -> SemVer:
    """Extract the semantic version from a Markdown file frontmatter."""

    with path.open("r", encoding="utf-8") as handle:
        first_line = handle.readline()
        if first_line.strip() != "---":
            raise SyncError(f"File '{path}' does not start with YAML frontmatter.")

        frontmatter_lines = []
        for line in handle:
            if line.strip() == "---":
                break
            frontmatter_lines.append(line)
        else:
            raise SyncError(f"Frontmatter in '{path}' is missing a closing '---'.")

    version_value = None
    for line in frontmatter_lines:
        column = line.split(":", 1)
        if len(column) != 2:
            continue
        key, value = (item.strip() for item in column)
        if key == "version":
            version_value = value
            break

    if version_value is None:
        raise SyncError(f"No 'version' key found in frontmatter for '{path}'.")

    return SemVer.parse(version_value)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Copy DOCS_SYSTEM_INSTRUCTION_SET.md into a destination repository, "
            "skipping when the destination already has the same or newer version."
        )
    )
    parser.add_argument(
        "destination",
        type=Path,
        help="Path to the destination repository root (or any base directory).",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help=(
            "Relative path inside the destination where the instruction set should be "
            f"placed (default: {DEFAULT_TARGET})."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Copy even when the destination version is newer or equal (downgrade).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without copying any files.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-error output.",
    )
    return parser


def log(message: str, *, quiet: bool) -> None:
    if not quiet:
        print(message)


def sync_instruction_set(
    destination: Path,
    target_relative: Path,
    *,
    force: bool,
    dry_run: bool,
    quiet: bool,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source_path = repo_root / "DOCS_SYSTEM_INSTRUCTION_SET.md"

    if not source_path.exists():
        raise SyncError(f"Source instruction set '{source_path}' not found.")

    destination = destination.expanduser().resolve()
    if not destination.exists():
        raise SyncError(f"Destination path '{destination}' does not exist.")

    target_path = (destination / target_relative).resolve()

    source_version = read_frontmatter_version(source_path)
    dest_version = None

    if target_path.exists():
        dest_version = read_frontmatter_version(target_path)
        comparison = source_version.compare(dest_version)
        if comparison < 0 and not force:
            raise SyncError(
                "Destination instruction set is newer. Use --force to overwrite."
            )
        if comparison == 0 and not force:
            log(
                "Destination already has the same version; nothing to do. "
                "Use --force to overwrite anyway.",
                quiet=quiet,
            )
            return

    action = "Would copy" if dry_run else "Copying"
    log(
        f"{action} instruction set {source_version} -> {target_path}"
        + (f" (replacing {dest_version})" if dest_version else ""),
        quiet=quiet,
    )

    if dry_run:
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    log("Sync complete.", quiet=quiet)


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        sync_instruction_set(
            destination=args.destination,
            target_relative=args.target,
            force=args.force,
            dry_run=args.dry_run,
            quiet=args.quiet,
        )
    except SyncError as exc:
        parser.exit(status=1, message=f"Error: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
