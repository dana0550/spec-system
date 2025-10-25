#!/usr/bin/env python3
"""Migrate legacy project docs into the spec system and run a code audit.

This utility performs three high-level tasks for a destination project:

1. Scans existing documentation (Markdown) to discover feature candidates,
   their descriptive text, and any inline status hints (done, in progress,
   not started, deprecated).
2. Walks the codebase to infer implementation status for the discovered
   features, relying on common patterns such as TODO/FIXME markers or
   deprecation annotations.
3. Emits a migration plan that maps the extracted information onto the
   Spec System structure (MASTER_SPEC, FEATURES, feature specs, product map).

Nothing is written unless `--apply` is provided. By default the script
produces a report on stdout and saves a markdown migration summary to the
destination directory so a contributor can review before committing.

The heuristics lean on human-readable cues (headings, checkboxes, keywords)
because legacy documentation varies widely. The output is therefore best
treated as a jump-start that still benefits from human review.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DOC_EXTENSIONS = {".md", ".markdown"}
CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".rb",
    ".go",
    ".java",
    ".kt",
    ".swift",
    ".m",
    ".mm",
    ".rs",
    ".php",
    ".scala",
    ".cs",
    ".cpp",
    ".cc",
    ".c",
    ".h",
    ".hpp",
    ".dart",
    ".sql",
}

SKIP_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "build",
    "dist",
    "out",
    "coverage",
    "__pycache__",
}

STATUS_KEYWORDS = {
    "done": ["done", "completed", "complete", "shipped", "released"],
    "in_progress": ["in progress", "wip", "working", "implementing", "building"],
    "not_started": ["not started", "todo", "backlog", "up next", "tbd", "planned"],
    "deprecated": ["deprecated", "retired", "obsolete", "sunset", "legacy"],
}

TODO_KEYWORDS = ["todo", "fixme", "wip", "tbd", "hack", "pending"]
DEPRECATED_KEYWORDS = ["deprecated", "@deprecated", "legacy", "sunset", "obsolete"]


@dataclass
class FeatureCandidate:
    """Represents a potential feature found in legacy artifacts."""

    name: str
    source_path: Path
    source_line: int
    summary: str = ""
    doc_status: Optional[str] = None
    code_status: Optional[str] = None
    evidence: List[str] = field(default_factory=list)
    id: Optional[str] = None

    def lifecycle(self) -> str:
        """Derive lifecycle for FEATURES.md (active vs deprecated)."""

        if (self.code_status or self.doc_status) == "deprecated":
            return "deprecated"
        return "active"

    def progress(self) -> str:
        """Final development status after combining doc + code audit."""

        if self.code_status:
            return self.code_status
        if self.doc_status:
            return self.doc_status
        return "unknown"


@dataclass
class MigrationArtifacts:
    """Holds the various outputs produced during migration analysis."""

    features: List[FeatureCandidate]
    master_spec_source: Optional[Path]
    report_path: Path
    product_map: str
    features_table: str
    feature_specs: Dict[str, str]


def normalize_status(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    candidate = text.strip().lower()
    for normalized, keywords in STATUS_KEYWORDS.items():
        for word in keywords:
            if word in candidate:
                return normalized
    return None


def strip_status_from_title(title: str) -> Tuple[str, Optional[str]]:
    """Remove inline status annotations from a heading or bullet line."""

    status = None
    cleaned = title
    match = re.search(r"[\[(]([^\]\)]+)[\])]", title)
    if match:
        status = normalize_status(match.group(1))
        cleaned = (title[: match.start()] + title[match.end() :]).strip()

    match = re.search(r"status\s*[:=]\s*(.+)$", cleaned, re.I)
    if match:
        status = normalize_status(match.group(1)) or status
        cleaned = cleaned[: match.start()].strip(" -–:\t")

    return cleaned.strip(" -–:"), status


def split_checkbox_body(body: str) -> Tuple[str, Optional[str]]:
    """Separate checkbox text into feature name and embedded status if present."""

    if " - " in body:
        name, remainder = body.split(" - ", 1)
        return name.strip(), normalize_status(remainder)
    return body.strip(), None


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return re.sub(r"-+", "-", slug).strip("-") or "feature"


def collect_markdown_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in DOC_EXTENSIONS:
            files.append(path)
    return sorted(files)


def extract_features_from_markdown(path: Path) -> List[FeatureCandidate]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    features: List[FeatureCandidate] = []
    in_features_section = False
    current_feature: Optional[FeatureCandidate] = None

    for idx, line in enumerate(lines):
        heading = re.match(r"^(#{2,6})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            raw_title = heading.group(2).strip()
            if level <= 2:
                in_features_section = bool(re.search(r"\bfeatures?\b", raw_title, re.I))
                current_feature = None
                continue

            title, inline_status = strip_status_from_title(raw_title)
            looks_like_feature = in_features_section or bool(
                re.search(r"\b(feature|capability|epic|workflow)\b", raw_title, re.I)
            )
            if not looks_like_feature:
                current_feature = None
                continue

            summary = collect_summary(lines, idx + 1, level)

            feature = FeatureCandidate(
                name=title,
                source_path=path,
                source_line=idx + 1,
                summary=summary,
                doc_status=inline_status,
            )
            features.append(feature)
            current_feature = feature
            continue

        checkbox = re.match(r"^[-*]\s*\[(?P<flag>[xX ])\]\s*(?P<body>.+)$", line)
        if checkbox:
            body, inline_status = split_checkbox_body(checkbox.group("body"))
            doc_status = inline_status
            if not doc_status:
                doc_status = "done" if checkbox.group("flag").lower() == "x" else "not_started"
            features.append(
                FeatureCandidate(
                    name=body,
                    source_path=path,
                    source_line=idx + 1,
                    summary=collect_summary(lines, idx + 1, 3),
                    doc_status=doc_status,
                )
            )
            continue

        status_line = re.match(r"^Status\s*[:=]\s*(.+)$", line, re.I)
        if status_line and current_feature:
            inferred = normalize_status(status_line.group(1))
            current_feature.doc_status = inferred or current_feature.doc_status

    return features


def collect_summary(lines: Sequence[str], start_index: int, heading_level: int) -> str:
    summary_lines: List[str] = []
    heading_break = re.compile(rf"^#{{1,{heading_level}}}\s+")
    for line in lines[start_index:]:
        if not line.strip():
            if summary_lines:
                break
            continue
        if heading_break.match(line):
            break
        if re.match(r"^[-*]\s*\[[xX ]\]", line):
            break
        summary_lines.append(line.rstrip())
        if len(summary_lines) >= 12:
            break
    return "\n".join(summary_lines).strip()


def deduplicate_features(features: Iterable[FeatureCandidate]) -> List[FeatureCandidate]:
    merged: Dict[str, FeatureCandidate] = {}
    for feature in features:
        key = feature.name.lower()
        if not key:
            continue
        existing = merged.get(key)
        if not existing:
            merged[key] = feature
            continue
        if not existing.doc_status and feature.doc_status:
            existing.doc_status = feature.doc_status
        if not existing.summary and feature.summary:
            existing.summary = feature.summary
        existing.source_line = min(existing.source_line, feature.source_line)
    return list(merged.values())


def collect_code_files(root: Path) -> List[Path]:
    results: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath, name)
            if path.suffix.lower() in CODE_EXTENSIONS:
                results.append(path)
    return results


def generate_feature_tokens(name: str) -> List[str]:
    tokens = {name.lower()}
    collapsed = re.sub(r"\s+", "", name).lower()
    tokens.add(collapsed)
    snake = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if snake:
        tokens.add(snake)
    camel = "".join(part.capitalize() for part in re.split(r"[^a-z0-9]", name) if part)
    if camel:
        tokens.add(camel)
        tokens.add(camel[0].lower() + camel[1:])
    return [token for token in tokens if token]


def perform_code_audit(features: List[FeatureCandidate], code_root: Path) -> None:
    code_files = collect_code_files(code_root)
    if not code_files:
        return

    for feature in features:
        tokens = generate_feature_tokens(feature.name)
        if not tokens:
            feature.code_status = feature.code_status or feature.doc_status
            continue

        evidence: List[str] = []
        found_any = False
        flagged_deprecated = False
        flagged_in_progress = False

        for code_path in code_files:
            try:
                with code_path.open("r", encoding="utf-8", errors="ignore") as handle:
                    for idx, line in enumerate(handle, start=1):
                        normalized_line = line.lower()
                        if not any(token in normalized_line for token in tokens):
                            continue
                        found_any = True
                        if len(evidence) < 6:
                            evidence.append(f"{code_path}:{idx}: {line.strip()}")
                        if any(keyword in normalized_line for keyword in DEPRECATED_KEYWORDS):
                            flagged_deprecated = True
                        if any(keyword in normalized_line for keyword in TODO_KEYWORDS):
                            flagged_in_progress = True
            except (UnicodeDecodeError, OSError):
                continue

        if not found_any:
            feature.code_status = feature.code_status or "not_started"
            continue

        if flagged_deprecated:
            feature.code_status = "deprecated"
        elif flagged_in_progress:
            feature.code_status = "in_progress"
        else:
            feature.code_status = "done"
        feature.evidence.extend(evidence)


def assign_feature_ids(features: List[FeatureCandidate]) -> None:
    for index, feature in enumerate(sorted(features, key=lambda f: f.name.lower()), start=1):
        feature.id = f"F-{index:03d}"


def ensure_docs_structure(destination: Path) -> None:
    docs_root = destination / "docs"
    (docs_root / "features").mkdir(parents=True, exist_ok=True)
    (docs_root / "DECISIONS").mkdir(parents=True, exist_ok=True)
    (docs_root / "templates").mkdir(parents=True, exist_ok=True)


def render_features_table(features: List[FeatureCandidate]) -> str:
    header = "| ID | Feature | Lifecycle | Progress | Source Doc |\n| --- | --- | --- | --- | --- |"
    rows = [
        f"| {feature.id} | {feature.name} | {feature.lifecycle()} | {feature.progress()} | {feature.source_path}#{feature.source_line} |"
        for feature in features
    ]
    return "\n".join([header] + rows)


def render_product_map(features: List[FeatureCandidate]) -> str:
    lines = ["# Product Map", ""]
    for feature in features:
        lines.append(f"- {feature.id} – {feature.name}")
    return "\n".join(lines) + "\n"


def render_feature_spec(feature: FeatureCandidate) -> str:
    summary = feature.summary or "_Summary migrated from legacy documentation. Flesh this out._"
    evidence_block = "\n".join(f"- {item}" for item in feature.evidence) or "- (No code references discovered)"
    lines = [
        f"# {feature.id} – {feature.name}",
        "",
        f"<!-- MIGRATED_FROM: {feature.source_path}#{feature.source_line} -->",
        "",
        "## Overview",
        "",
        textwrap.dedent(summary).strip() or "_TBD_",
        "",
        "## Requirements",
        "",
        "- _Refine based on legacy docs_",
        "",
        "## Acceptance Criteria",
        "",
        "- _Backfill during migration review_",
        "",
        "## Development Status",
        "",
        f"- Doc status: {feature.doc_status or 'unknown'}",
        f"- Code audit: {feature.code_status or 'unknown'}",
        "",
        "## Code Audit Evidence",
        "",
        evidence_block,
        "",
        "## Changelog",
        "",
        f"- {feature.source_path.name} → {feature.progress()} (initial migration)",
    ]
    return "\n".join(lines) + "\n"


def render_master_spec_placeholder(source: Optional[Path]) -> str:
    lines = [
        "# Master Spec",
        "",
        "This master spec was bootstrapped via `migrate_existing_project.py`. Review",
        "the legacy documentation and fill in the goals, principles, scope, and",
        "release plan before treating this as canonical.",
    ]
    if source:
        lines += ["", f"Legacy source: {source}"]
    return "\n".join(lines) + "\n"


def render_migration_report(features: List[FeatureCandidate], report_path: Path) -> str:
    rows = []
    for feature in features:
        evidence = feature.evidence[:3]
        evidence_text = "\n".join(f"    - {item}" for item in evidence) or "    - (none)"
        rows.append(
            textwrap.dedent(
                f"""
                ### {feature.id} – {feature.name}

                - Doc status: {feature.doc_status or 'unknown'}
                - Code audit: {feature.code_status or 'unknown'}
                - Source: {feature.source_path}#{feature.source_line}
{evidence_text}
                """
            ).strip()
        )

    content = (
        f"# Migration Report\n\n"
        f"Generated by `migrate_existing_project.py`.\n\n"
        + "\n\n".join(rows)
        + "\n"
    )
    report_path.write_text(content, encoding="utf-8")
    return content


def apply_artifacts(destination: Path, artifacts: MigrationArtifacts, force: bool) -> None:
    docs_root = destination / "docs"
    ensure_docs_structure(destination)

    master_spec_path = docs_root / "MASTER_SPEC.md"
    if force or not master_spec_path.exists():
        master_spec_path.write_text(
            render_master_spec_placeholder(artifacts.master_spec_source),
            encoding="utf-8",
        )

    features_path = docs_root / "FEATURES.md"
    if force or not features_path.exists():
        features_path.write_text(artifacts.features_table + "\n", encoding="utf-8")

    product_map_path = docs_root / "PRODUCT_MAP.md"
    if force or not product_map_path.exists():
        product_map_path.write_text(artifacts.product_map, encoding="utf-8")

    for feature in artifacts.features:
        slug = slugify(feature.name)
        feature_path = docs_root / "features" / f"{feature.id}-{slug}.md"
        if feature_path.exists() and not force:
            continue
        feature_path.write_text(render_feature_spec(feature), encoding="utf-8")


def build_artifacts(
    destination: Path,
    features: List[FeatureCandidate],
    master_spec_source: Optional[Path],
    report_filename: str,
) -> MigrationArtifacts:
    report_path = destination / report_filename
    features_table = render_features_table(features)
    product_map = render_product_map(features)

    feature_specs = {feature.id: render_feature_spec(feature) for feature in features}

    return MigrationArtifacts(
        features=features,
        master_spec_source=master_spec_source,
        report_path=report_path,
        product_map=product_map,
        features_table=features_table,
        feature_specs=feature_specs,
    )


def find_master_spec_source(markdown_files: Sequence[Path]) -> Optional[Path]:
    for path in markdown_files:
        lower_name = path.name.lower()
        if any(keyword in lower_name for keyword in ("master", "prd", "overview", "vision")):
            return path
    return markdown_files[0] if markdown_files else None


def run_migration(args: argparse.Namespace) -> None:
    source = Path(args.source).resolve()
    destination = Path(args.destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    markdown_files = collect_markdown_files(source)
    if not markdown_files:
        raise SystemExit(f"No Markdown documents discovered under {source}")

    feature_candidates: List[FeatureCandidate] = []
    for path in markdown_files:
        feature_candidates.extend(extract_features_from_markdown(path))

    features = deduplicate_features(feature_candidates)
    if not features:
        raise SystemExit("Unable to locate feature candidates in legacy documentation")

    assign_feature_ids(features)

    if args.audit:
        perform_code_audit(features, source)

    report_filename = args.report
    artifacts = build_artifacts(destination, features, find_master_spec_source(markdown_files), report_filename)
    render_migration_report(features, artifacts.report_path)

    if args.apply:
        apply_artifacts(destination, artifacts, force=args.force)

    summary = {
        "feature_count": len(features),
        "report": str(artifacts.report_path),
        "applied": bool(args.apply),
        "destination": str(destination),
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("Migration plan prepared:")
        print(json.dumps(summary, indent=2))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Path to the legacy project root")
    parser.add_argument(
        "--destination",
        required=True,
        help="Location to write spec system artifacts (often same as --source)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write spec files (FEATURES.md, feature specs, etc.) instead of just reporting",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing spec files when used with --apply",
    )
    parser.add_argument(
        "--report",
        default="MIGRATION_REPORT.md",
        help="File name for the generated migration report",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable summary on stdout",
    )
    parser.add_argument(
        "--no-audit",
        dest="audit",
        action="store_false",
        help="Skip the code audit phase",
    )
    parser.set_defaults(audit=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    run_migration(args)


if __name__ == "__main__":
    main()
