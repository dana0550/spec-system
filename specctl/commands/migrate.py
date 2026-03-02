from __future__ import annotations

import re
import shutil
import tempfile
from argparse import Namespace
from pathlib import Path

from specctl.feature_index import FeatureRow, read_feature_rows, write_feature_rows
from specctl.io_utils import now_date, now_timestamp, slugify, write_text
from specctl.validators.project import lint_project


REQ_V1_RE = re.compile(r"^\s*[-*]\s*R\d+\s*:\s*(.+)$", re.IGNORECASE)
AC_V1_RE = re.compile(r"^\s*[-*]\s*AC\d+\s*:\s*(.+)$", re.IGNORECASE)
LEGACY_STATUS_MAP = {
    "proposed": "requirements_draft",
    "not_started": "requirements_draft",
    "active": "implementing",
    "in_progress": "implementing",
    "done": "done",
    "deprecated": "deprecated",
    "requirements_draft": "requirements_draft",
    "requirements_approved": "requirements_approved",
    "design_draft": "design_draft",
    "design_approved": "design_approved",
    "tasks_draft": "tasks_draft",
    "tasks_approved": "tasks_approved",
    "implementing": "implementing",
    "verifying": "verifying",
}


def run(args) -> int:
    root = Path(args.root).resolve()
    docs = root / "docs"

    backup_dir = root / ".specctl-backups" / f"migrate-{now_timestamp()}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    if docs.exists():
        shutil.copytree(docs, backup_dir / "docs", dirs_exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="specctl-migrate-", dir=root) as tmpdir:
        staged_root = Path(tmpdir)
        staged_docs = staged_root / "docs"
        if docs.exists():
            shutil.copytree(docs, staged_docs)
        else:
            staged_docs.mkdir(parents=True, exist_ok=True)

        migration_error = _migrate_docs(staged_docs)
        if migration_error:
            print(f"[ERROR] {migration_error}")
            return 1

        from specctl.commands import render

        render_rc = render.run(Namespace(root=str(staged_root), check=False))
        if render_rc != 0:
            print("[ERROR] Migration render step failed")
            return 1

        messages, _ = lint_project(staged_root)
        errors = [m for m in messages if m.severity == "ERROR"]
        if errors:
            print("[ERROR] Migration completed with blocking issues:")
            for msg in errors:
                print(f"- {msg.code}: {msg.message}")
            return 1

        if docs.exists():
            shutil.rmtree(docs)
        shutil.copytree(staged_docs, docs)

    print(f"Migration complete. Backup created at {backup_dir}")
    return 0


def _migrate_docs(docs: Path) -> str | None:
    _ensure_base_v2_docs(docs)

    features_path = docs / "FEATURES.md"
    v1_feature_rows = read_feature_rows(features_path)
    if not v1_feature_rows:
        return "No features found in docs/FEATURES.md"

    migrated_rows: list[FeatureRow] = []
    report_lines = ["# Migration Report", "", f"Date: {now_date()}", ""]

    for row in v1_feature_rows:
        old_spec = docs / row.spec_path
        if not old_spec.exists():
            return f"Missing v1 spec file: {old_spec}"

        feature_slug = f"{row.feature_id}-{slugify(row.name)}"
        feature_dir = docs / "features" / feature_slug
        feature_dir.mkdir(parents=True, exist_ok=True)

        old_text = old_spec.read_text(encoding="utf-8")
        req_statements = [m.group(1).strip() for m in REQ_V1_RE.finditer(old_text)]
        ac_statements = [m.group(1).strip() for m in AC_V1_RE.finditer(old_text)]

        if not req_statements:
            req_statements = ["WHEN the feature is requested, the system MUST execute the primary behavior."]
        if not ac_statements:
            ac_statements = ["Given the feature is configured When invoked Then the result is successful."]

        feature_digits = row.feature_id.replace("-", "")

        req_lines = [
            f"- R-{feature_digits}-{idx:03d}: {statement}"
            for idx, statement in enumerate(req_statements, start=1)
        ]
        scenario_lines = [
            f"- S-{feature_digits}-{idx:03d}: {statement}"
            for idx, statement in enumerate(ac_statements, start=1)
        ]

        mapped_status = _map_legacy_status(row.status)
        if mapped_status != row.status:
            report_lines.append(f"- Status mapped for {row.feature_id}: '{row.status}' -> '{mapped_status}'")

        write_text(
            feature_dir / "requirements.md",
            "\n".join(
                [
                    "---",
                    "doc_type: feature_requirements",
                    f"feature_id: {row.feature_id}",
                    f"name: {row.name}",
                    f"status: {mapped_status}",
                    f"owner: {row.owner}",
                    f"last_updated: {now_date()}",
                    "---",
                    f"# {row.name} Requirements",
                    "",
                    *req_lines,
                    *scenario_lines,
                    "",
                ]
            ),
        )

        write_text(
            feature_dir / "design.md",
            "\n".join(
                [
                    "---",
                    "doc_type: feature_design",
                    f"feature_id: {row.feature_id}",
                    f"status: {mapped_status}",
                    f"last_updated: {now_date()}",
                    "---",
                    f"# {row.name} Design",
                    "",
                    *[
                        f"- D-{feature_digits}-{idx:03d}: Implements R-{feature_digits}-{idx:03d}"
                        for idx in range(1, len(req_lines) + 1)
                    ],
                    "",
                ]
            ),
        )

        write_text(
            feature_dir / "tasks.md",
            "\n".join(
                [
                    "---",
                    "doc_type: feature_tasks",
                    f"feature_id: {row.feature_id}",
                    f"status: {mapped_status}",
                    f"last_updated: {now_date()}",
                    "---",
                    f"# {row.name} Tasks",
                    "",
                    *[
                        f"- [ ] T-{feature_digits}-{idx:03d} Implement requirement (R: R-{feature_digits}-{idx:03d}, D: D-{feature_digits}-{idx:03d})"
                        for idx in range(1, len(req_lines) + 1)
                    ],
                    "",
                ]
            ),
        )

        write_text(
            feature_dir / "verification.md",
            "\n".join(
                [
                    "---",
                    "doc_type: feature_verification",
                    f"feature_id: {row.feature_id}",
                    f"status: {mapped_status}",
                    f"last_updated: {now_date()}",
                    "---",
                    f"# {row.name} Verification",
                    "",
                    *[
                        f"- S-{feature_digits}-{idx:03d}: {statement}"
                        for idx, statement in enumerate(ac_statements, start=1)
                    ],
                    *[
                        f"Evidence: S-{feature_digits}-{idx:03d} -> TBD"
                        for idx in range(1, len(ac_statements) + 1)
                    ],
                    "",
                ]
            ),
        )

        migrated_rows.append(
            FeatureRow(
                feature_id=row.feature_id,
                name=row.name,
                status=mapped_status,
                parent_id=row.parent_id,
                spec_path=f"features/{feature_slug}/requirements.md",
                owner=row.owner,
                aliases=row.aliases,
            )
        )
        report_lines.append(
            f"- Migrated {row.feature_id} -> docs/features/{feature_slug}/{{requirements,design,tasks,verification}}.md"
        )

    write_feature_rows(features_path, migrated_rows)
    write_text(docs / "MIGRATION_REPORT.md", "\n".join(report_lines) + "\n")
    return None


def _ensure_base_v2_docs(docs: Path) -> None:
    base_files = {
        "MASTER_SPEC.md": "\n".join(
            [
                "---",
                "doc_type: master_spec",
                "product_name: Migrated Product",
                "version: 2.0.0",
                "status: active",
                "owners: []",
                f"last_reviewed: {now_date()}",
                "---",
                "# Master Spec",
                "",
            ]
        )
        + "\n",
        "STEERING.md": "\n".join(
            [
                "---",
                "doc_type: steering",
                "version: 2.0.0",
                f"last_reviewed: {now_date()}",
                "---",
                "# Steering",
                "",
            ]
        )
        + "\n",
        "PRODUCT_MAP.md": "\n".join(
            [
                "---",
                "doc_type: product_map",
                "from_index: ./FEATURES.md",
                f"last_rendered: {now_date()}",
                "---",
                "# Product Map",
                "",
            ]
        )
        + "\n",
        "TRACEABILITY.md": "\n".join(
            [
                "---",
                "doc_type: traceability",
                "version: 2.0.0",
                f"last_rendered: {now_date()}",
                "---",
                "# Traceability Report",
                "",
            ]
        )
        + "\n",
    }
    for name, content in base_files.items():
        path = docs / name
        if not path.exists():
            write_text(path, content)


def _map_legacy_status(status: str) -> str:
    normalized = status.strip().lower()
    return LEGACY_STATUS_MAP.get(normalized, "requirements_draft")
