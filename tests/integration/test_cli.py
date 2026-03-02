from __future__ import annotations

import re
import shutil
from pathlib import Path

from specctl.cli import main


def copy_fixture(tmp_path: Path, fixture_root: Path) -> Path:
    target = tmp_path / "repo"
    shutil.copytree(fixture_root, target)
    return target


def test_init_creates_valid_structure(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert (root / "docs" / "FEATURES.md").exists()


def test_full_feature_lifecycle(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert (
        main(
            [
                "feature",
                "create",
                "--root",
                str(root),
                "--name",
                "Login",
                "--status",
                "requirements_draft",
                "--owner",
                "owner@example.com",
            ]
        )
        == 0
    )
    assert main(["approve", "--root", str(root), "--feature-id", "F-001", "--phase", "requirements"]) == 0
    _assert_feature_status(root, "F-001", "requirements_approved")


def test_design_and_tasks_approvals_sync_frontmatter(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert (
        main(
            [
                "feature",
                "create",
                "--root",
                str(root),
                "--name",
                "DesignFeature",
                "--status",
                "design_draft",
                "--owner",
                "owner@example.com",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "feature",
                "create",
                "--root",
                str(root),
                "--name",
                "TasksFeature",
                "--status",
                "tasks_draft",
                "--owner",
                "owner@example.com",
            ]
        )
        == 0
    )
    assert main(["approve", "--root", str(root), "--feature-id", "F-001", "--phase", "design"]) == 0
    assert main(["approve", "--root", str(root), "--feature-id", "F-002", "--phase", "tasks"]) == 0
    _assert_feature_status(root, "F-001", "design_approved")
    _assert_feature_status(root, "F-002", "tasks_approved")


def test_feature_create_requires_existing_parent(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert (
        main(
            [
                "feature",
                "create",
                "--root",
                str(root),
                "--name",
                "ChildFeature",
                "--parent-id",
                "F-999",
            ]
        )
        == 1
    )


def test_migrate_valid_v1_fixture(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/v1_docs")
    root = copy_fixture(tmp_path, fixture)
    assert main(["migrate-v1-to-v2", "--root", str(root)]) == 0
    assert (root / "docs" / "features" / "F-001-login" / "requirements.md").exists()
    features_text = (root / "docs" / "FEATURES.md").read_text(encoding="utf-8")
    assert "| F-001 | Login | implementing |" in features_text

    backups = sorted((root / ".specctl-backups").glob("migrate-*"))
    assert backups
    backup_docs = backups[-1] / "docs"
    assert (backup_docs / "FEATURES.md").exists()
    assert (backup_docs / "features" / "F-001-login.md").exists()
    assert not (backup_docs / "MASTER_SPEC.md").exists()


def test_migrate_invalid_fixture_fails(tmp_path: Path) -> None:
    root = tmp_path / "badrepo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "FEATURES.md").write_text(
        "| ID | Name | Status | Parent ID | Spec Path | Owner | Aliases |\n"
        "|----|------|--------|-----------|-----------|-------|---------|\n"
        "| F-001 | MissingFile | requirements_draft |  | features/missing.md | owner@example.com | [] |\n",
        encoding="utf-8",
    )
    assert main(["migrate-v1-to-v2", "--root", str(root)]) == 1


def test_render_is_deterministic(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/v2_docs")
    root = copy_fixture(tmp_path, fixture)
    assert main(["render", "--root", str(root)]) == 0
    first_product_map = (root / "docs" / "PRODUCT_MAP.md").read_text(encoding="utf-8")
    first_traceability = (root / "docs" / "TRACEABILITY.md").read_text(encoding="utf-8")
    assert main(["render", "--root", str(root)]) == 0
    assert (root / "docs" / "PRODUCT_MAP.md").read_text(encoding="utf-8") == first_product_map
    assert (root / "docs" / "TRACEABILITY.md").read_text(encoding="utf-8") == first_traceability


def test_deprecated_status_is_allowed(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert (
        main(
            [
                "feature",
                "create",
                "--root",
                str(root),
                "--name",
                "LegacyFeature",
                "--status",
                "deprecated",
                "--owner",
                "owner@example.com",
            ]
        )
        == 0
    )
    assert main(["render", "--root", str(root)]) == 0
    assert main(["check", "--root", str(root)]) == 0


def test_done_status_with_evidence_passes_check(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert (
        main(
            [
                "feature",
                "create",
                "--root",
                str(root),
                "--name",
                "CompletedFeature",
                "--status",
                "done",
                "--owner",
                "owner@example.com",
            ]
        )
        == 0
    )
    assert main(["render", "--root", str(root)]) == 0
    assert main(["check", "--root", str(root)]) == 0


def test_pr_template_contains_required_sections() -> None:
    template_path = Path(".github/PULL_REQUEST_TEMPLATE/docs-system.md")
    text = template_path.read_text(encoding="utf-8")
    required_tokens = [
        "## Traceability Coverage",
        "## Phase Approvals",
        "## Validation Evidence",
        "## Migration Notes (if applicable)",
        "`specctl check`",
    ]
    for token in required_tokens:
        assert token in text


def test_bugfix_template_contains_regression_flow() -> None:
    template_path = Path("skills/docs-spec-system/assets/templates/BUGFIX_SPEC_TEMPLATE.md")
    text = template_path.read_text(encoding="utf-8")
    required_tokens = [
        "## Regression Scenario",
        "## Requirement Update",
        "## Design Update",
        "## Tasks",
        "## Verification Evidence",
        "Evidence: S-FXXX-900",
    ]
    for token in required_tokens:
        assert token in text


def _assert_feature_status(root: Path, feature_id: str, expected_status: str) -> None:
    features_text = (root / "docs" / "FEATURES.md").read_text(encoding="utf-8")
    row_pattern = re.compile(
        rf"^\|\s*{re.escape(feature_id)}\s*\|[^|]+\|\s*{re.escape(expected_status)}\s*\|",
        re.MULTILINE,
    )
    assert row_pattern.search(features_text)

    feature_dir = next((root / "docs" / "features").glob(f"{feature_id}-*"))
    for filename in ["requirements.md", "design.md", "tasks.md", "verification.md"]:
        text = (feature_dir / filename).read_text(encoding="utf-8")
        assert f"status: {expected_status}" in text
