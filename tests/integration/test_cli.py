from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import yaml

from specctl.cli import main
from specctl.commands import check as check_command
from specctl.commands import epic_create as epic_create_command
from specctl.commands import render as render_command
from specctl.feature_index import read_feature_rows
from specctl.oneshot_utils import parse_blockers
from specctl.validators.project import lint_project as real_lint_project


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


def test_feature_create_keeps_scenario_text_consistent_across_files(tmp_path: Path) -> None:
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
                "ScenarioConsistency",
                "--owner",
                "owner@example.com",
            ]
        )
        == 0
    )
    feature_dir = next((root / "docs" / "features").glob("F-001-*"))
    req_text = (feature_dir / "requirements.md").read_text(encoding="utf-8")
    ver_text = (feature_dir / "verification.md").read_text(encoding="utf-8")
    expected = "Given valid input When the request is submitted Then the response status is 200."
    assert f"- S-F001-001: {expected}" in req_text
    assert f"- S-F001-001: {expected}" in ver_text


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


def test_feature_name_with_pipe_roundtrips_in_features_index(tmp_path: Path) -> None:
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
                "Login|Admin",
                "--owner",
                "owner@example.com",
            ]
        )
        == 0
    )
    rows = read_feature_rows(root / "docs" / "FEATURES.md")
    assert rows[0].name == "Login|Admin"
    assert rows[0].status == "requirements_draft"


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


def test_feature_create_rejects_invalid_status_and_feature_id(tmp_path: Path) -> None:
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
                "InvalidStatus",
                "--status",
                "totally_invalid",
            ]
        )
        == 1
    )
    assert (
        main(
            [
                "feature",
                "create",
                "--root",
                str(root),
                "--name",
                "InvalidId",
                "--feature-id",
                "bad-id",
            ]
        )
        == 1
    )


def test_approve_fails_when_required_feature_files_are_missing(tmp_path: Path) -> None:
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
                "ApprovalGuard",
                "--status",
                "requirements_draft",
                "--owner",
                "owner@example.com",
            ]
        )
        == 0
    )
    feature_dir = next((root / "docs" / "features").glob("F-001-*"))
    (feature_dir / "design.md").unlink()
    assert main(["approve", "--root", str(root), "--feature-id", "F-001", "--phase", "requirements"]) == 1


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


def test_migrate_ignores_lowercase_requirement_like_bullets(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/v1_docs")
    root = copy_fixture(tmp_path, fixture)
    old_spec = root / "docs" / "features" / "F-001-login.md"
    old_spec.write_text(
        old_spec.read_text(encoding="utf-8")
        + "\n## Notes\n- r100: fallback mode.\n- ac100: any healthy response.\n",
        encoding="utf-8",
    )

    assert main(["migrate-v1-to-v2", "--root", str(root)]) == 0
    requirements_text = (root / "docs" / "features" / "F-001-login" / "requirements.md").read_text(
        encoding="utf-8"
    )
    assert "fallback mode." not in requirements_text
    assert "any healthy response." not in requirements_text


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
    assert not (root / "docs" / "MASTER_SPEC.md").exists()
    assert not (root / "docs" / "PRODUCT_MAP.md").exists()
    assert not (root / "docs" / "TRACEABILITY.md").exists()


def test_render_is_deterministic(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/v2_docs")
    root = copy_fixture(tmp_path, fixture)
    assert main(["render", "--root", str(root)]) == 0
    first_product_map = (root / "docs" / "PRODUCT_MAP.md").read_text(encoding="utf-8")
    first_traceability = (root / "docs" / "TRACEABILITY.md").read_text(encoding="utf-8")
    assert main(["render", "--root", str(root)]) == 0
    assert (root / "docs" / "PRODUCT_MAP.md").read_text(encoding="utf-8") == first_product_map
    assert (root / "docs" / "TRACEABILITY.md").read_text(encoding="utf-8") == first_traceability


def test_render_uses_features_last_synced_stamp(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "Stamped", "--owner", "owner@example.com"]) == 0
    features_path = root / "docs" / "FEATURES.md"
    text = features_path.read_text(encoding="utf-8")
    text = re.sub(r"^last_synced: .*$", "last_synced: 2001-02-03", text, flags=re.MULTILINE)
    features_path.write_text(text, encoding="utf-8")

    assert main(["render", "--root", str(root)]) == 0
    product_map_text = (root / "docs" / "PRODUCT_MAP.md").read_text(encoding="utf-8")
    traceability_text = (root / "docs" / "TRACEABILITY.md").read_text(encoding="utf-8")
    assert "last_rendered: 2001-02-03" in product_map_text
    assert "last_rendered: 2001-02-03" in traceability_text
    assert main(["render", "--root", str(root), "--check"]) == 0


def test_init_outputs_use_single_trailing_newline(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    docs = root / "docs"
    for filename in ["MASTER_SPEC.md", "STEERING.md", "FEATURES.md", "PRODUCT_MAP.md"]:
        content = (docs / filename).read_text(encoding="utf-8")
        assert content.endswith("\n")
        assert not content.endswith("\n\n")


def test_hierarchy_cycle_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "FeatureA", "--owner", "owner@example.com"]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "FeatureB", "--owner", "owner@example.com"]) == 0

    features_path = root / "docs" / "FEATURES.md"
    text = features_path.read_text(encoding="utf-8")
    text = text.replace("| F-001 | FeatureA | requirements_draft |  |", "| F-001 | FeatureA | requirements_draft | F-002 |")
    text = text.replace("| F-002 | FeatureB | requirements_draft |  |", "| F-002 | FeatureB | requirements_draft | F-001 |")
    features_path.write_text(text, encoding="utf-8")

    assert main(["lint", "--root", str(root)]) == 1


def test_traceability_checks_use_exact_requirement_ids(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "TraceExact", "--owner", "owner@example.com"]) == 0
    feature_dir = next((root / "docs" / "features").glob("F-001-*"))
    (feature_dir / "design.md").write_text(
        "---\n"
        "doc_type: feature_design\n"
        "feature_id: F-001\n"
        "status: requirements_draft\n"
        "last_updated: 2026-03-01\n"
        "---\n"
        "# TraceExact Design\n\n"
        "- D-F001-010: Implements R-F001-0010\n",
        encoding="utf-8",
    )
    (feature_dir / "tasks.md").write_text(
        "---\n"
        "doc_type: feature_tasks\n"
        "feature_id: F-001\n"
        "status: requirements_draft\n"
        "last_updated: 2026-03-01\n"
        "---\n"
        "# TraceExact Tasks\n\n"
        "- [ ] T-F001-010 Implement requirement (R: R-F001-0010, D: D-F001-010)\n",
        encoding="utf-8",
    )
    assert main(["lint", "--root", str(root)]) == 1


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


def test_check_reuses_lint_stats_for_render(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "CheckOnce", "--owner", "owner@example.com"]) == 0
    assert main(["render", "--root", str(root)]) == 0

    calls = {"check": 0, "render": 0}

    def check_lint_wrapper(path: Path):
        calls["check"] += 1
        return real_lint_project(path)

    def render_lint_wrapper(path: Path):
        calls["render"] += 1
        return real_lint_project(path)

    monkeypatch.setattr(check_command, "lint_project", check_lint_wrapper)
    monkeypatch.setattr(render_command, "lint_project", render_lint_wrapper)

    assert main(["check", "--root", str(root)]) == 0
    assert calls["check"] == 1
    assert calls["render"] == 0


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


def _write_epic_brief(path: Path, *, include_ui: bool = False) -> None:
    vision = "- Deliver account orchestration and reporting."
    if include_ui:
        vision = "- Deliver account orchestration and reporting dashboard."
    path.write_text(
        "\n".join(
            [
                "# Example Epic",
                "",
                "## Vision",
                vision,
                "",
                "## Outcomes",
                "- Improve setup reliability",
                "- Improve operational insight",
                "",
                "## User Journeys",
                "- Admin provisions tenant",
                "- Admin reviews onboarding status",
                "",
                "## Constraints",
                "- Must preserve existing API compatibility",
                "",
                "## Non-Goals",
                "- No billing changes",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_feature_check_command_passes_for_scaffolded_feature(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "FeatureCheck", "--owner", "owner@example.com"]) == 0
    assert main(["feature", "check", "--root", str(root), "--feature-id", "F-001"]) == 0


def test_epic_create_scaffolds_feature_tree_and_contract(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    _write_epic_brief(brief_path, include_ui=True)
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "Account Onboarding",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
            ]
        )
        == 0
    )

    epics_text = (root / "docs" / "EPICS.md").read_text(encoding="utf-8")
    assert "| E-001 | Account Onboarding | implementing | F-001 |" in epics_text
    rows = read_feature_rows(root / "docs" / "FEATURES.md")
    assert len(rows) == 13
    assert rows[0].feature_id == "F-001"
    assert any(row.feature_id == "F-001.01.05" for row in rows)

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    oneshot = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    assert oneshot["epic_id"] == "E-001"
    assert len(oneshot["scope_feature_ids"]) == 13
    assert len(oneshot["checkpoint_graph"]) == 13
    assert oneshot["checkpoint_graph"][0]["depends_on"] == []
    assert oneshot["checkpoint_graph"][1]["depends_on"] == [oneshot["checkpoint_graph"][0]["checkpoint_id"]]


def test_epic_create_returns_error_when_render_fails(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    _write_epic_brief(brief_path)

    monkeypatch.setattr(epic_create_command.render, "run", lambda _args: 1)
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "RenderFailure",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
            ]
        )
        == 1
    )


def test_oneshot_check_fails_when_validation_commands_missing(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    _write_epic_brief(brief_path)
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "MissingValidationCommands",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
            ]
        )
        == 0
    )
    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    payload = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    payload["validation_commands"] = []
    (epic_dir / "oneshot.yaml").write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    assert main(["oneshot", "check", "--root", str(root), "--epic-id", "E-001"]) == 1


def test_oneshot_run_uses_soft_blocker_for_non_integrity_failure(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    _write_epic_brief(brief_path)
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "SoftBlockerFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
            ]
        )
        == 0
    )

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    payload = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    payload["repair_policy"]["max_retries_per_checkpoint"] = 0
    payload["checkpoint_graph"][0]["validation_commands"] = [
        "python -c \"import sys; sys.exit(0)\"",
        "python -c \"import sys; sys.exit(1)\"",
    ]
    (epic_dir / "oneshot.yaml").write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    run_dir = next((epic_dir / "runs").iterdir())
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    first_checkpoint = payload["checkpoint_graph"][0]["checkpoint_id"]
    assert state["status"] == "stabilizing"
    assert state["checkpoint_status"][first_checkpoint] == "blocked_with_placeholder"


def test_oneshot_run_empty_validation_commands_passes_without_blockers(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    _write_epic_brief(brief_path)
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "EmptyValidationFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
            ]
        )
        == 0
    )

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    payload = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    payload["validation_commands"] = []
    for checkpoint in payload["checkpoint_graph"]:
        checkpoint["validation_commands"] = []
    (epic_dir / "oneshot.yaml").write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    run_dir = next((epic_dir / "runs").iterdir())
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    blockers = (run_dir / "blockers.md").read_text(encoding="utf-8")
    assert state["status"] == "ready_to_finalize"
    assert "B-E001-" not in blockers


def test_oneshot_run_and_finalize_marks_scope_done(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    _write_epic_brief(brief_path)
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "FinalizeFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
            ]
        )
        == 0
    )

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    run_dir = next((epic_dir / "runs").iterdir())
    run_id = run_dir.name
    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 0

    epics_text = (root / "docs" / "EPICS.md").read_text(encoding="utf-8")
    assert "| E-001 | FinalizeFlow | done |" in epics_text
    rows = read_feature_rows(root / "docs" / "FEATURES.md")
    scope_ids = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))["scope_feature_ids"]
    for row in rows:
        if row.feature_id in scope_ids:
            assert row.status == "done"


def test_oneshot_finalize_fails_with_open_blockers(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    _write_epic_brief(brief_path)
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "BlockerFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
            ]
        )
        == 0
    )
    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    payload = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    payload["validation_commands"] = ["false"]
    (epic_dir / "oneshot.yaml").write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    run_dir = next((epic_dir / "runs").iterdir())
    run_id = run_dir.name
    blockers = (run_dir / "blockers.md").read_text(encoding="utf-8")
    assert "B-E001-001" in blockers
    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 1


def test_oneshot_resume_resolves_blockers_for_passed_checkpoints(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    _write_epic_brief(brief_path)
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "ResumeResolveBlockerFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
            ]
        )
        == 0
    )

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    oneshot_path = epic_dir / "oneshot.yaml"
    payload = yaml.safe_load(oneshot_path.read_text(encoding="utf-8"))
    payload["validation_commands"] = ["false"]
    oneshot_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    run_dir = next((epic_dir / "runs").iterdir())
    run_id = run_dir.name
    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 1

    payload["validation_commands"] = ["true"]
    oneshot_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    assert main(["oneshot", "resume", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 0

    blockers = parse_blockers(run_dir / "blockers.md")
    assert blockers
    assert all(row["status"] != "open" for row in blockers)
    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 0
