from __future__ import annotations

from collections import Counter
import json
import re
import shutil
from pathlib import Path

import yaml

from specctl.cli import main
from specctl.commands import check as check_command
from specctl.commands import epic_create as epic_create_command
from specctl.commands import oneshot_finalize as oneshot_finalize_command
from specctl.commands import oneshot_resume as oneshot_resume_command
from specctl.commands import render as render_command
from specctl.commands import report as report_command
from specctl.constants import NEEDS_INPUT_EXIT_CODE
from specctl.feature_index import read_feature_rows
from specctl.models import OneShotStats, TraceabilityStats
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
    assert main(["impact", "refresh", "--root", str(root), "--feature-id", "F-001"]) == 0
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
    assert main(["impact", "refresh", "--root", str(root), "--feature-id", "F-001"]) == 0
    assert main(["impact", "refresh", "--root", str(root), "--feature-id", "F-002"]) == 0
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


def test_migrate_existing_v2_fixture_is_non_destructive(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/v2_docs")
    root = copy_fixture(tmp_path, fixture)
    feature_dir = root / "docs" / "features" / "F-001-login"
    before = {
        name: (feature_dir / name).read_text(encoding="utf-8")
        for name in ("requirements.md", "design.md", "tasks.md", "verification.md")
    }

    assert main(["migrate-v1-to-v2", "--root", str(root)]) == 0

    after = {
        name: (feature_dir / name).read_text(encoding="utf-8")
        for name in ("requirements.md", "design.md", "tasks.md", "verification.md")
    }
    assert after == before
    report_text = (root / "docs" / "MIGRATION_REPORT.md").read_text(encoding="utf-8")
    assert "Detected existing v2 feature layout; no feature artifacts were rewritten." in report_text


def test_migrate_existing_v2_fixture_backfills_epics_index(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/v2_docs")
    root = copy_fixture(tmp_path, fixture)
    (root / "docs" / "EPICS.md").unlink()
    shutil.rmtree(root / "docs" / "epics", ignore_errors=True)
    requirements_before = (root / "docs" / "features" / "F-001-login" / "requirements.md").read_text(
        encoding="utf-8"
    )

    assert main(["migrate-v1-to-v2", "--root", str(root)]) == 0

    assert (root / "docs" / "EPICS.md").exists()
    assert (root / "docs" / "epics").exists()
    requirements_after = (root / "docs" / "features" / "F-001-login" / "requirements.md").read_text(
        encoding="utf-8"
    )
    assert requirements_after == requirements_before


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


def test_report_json_includes_runs_total(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    def lint_stub(_root: Path):
        return [], TraceabilityStats(), OneShotStats(epics_total=2, runs_total=7), None

    monkeypatch.setattr(report_command, "lint_project_with_impact", lint_stub)
    assert main(["report", "--root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["epics_total"] == 2
    assert payload["runs_total"] == 7
    assert payload["impact_suspects_open"] == 0
    assert payload["impact_features_tracked"] == 0


def test_impact_scan_json_schema_and_refresh_flow(tmp_path: Path, capsys) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "ImpactFlow", "--owner", "owner@example.com"]) == 0
    capsys.readouterr()

    assert main(["impact", "scan", "--root", str(root), "--feature-id", "F-001", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["baseline_status"] == "ok"
    assert payload["suspects_open"] > 0
    assert payload["features_scanned"] == 1
    assert {"feature_id", "entity_type", "entity_id", "reason", "upstream_ids", "path", "line"} <= set(
        payload["suspects"][0]
    )

    assert main(["impact", "refresh", "--root", str(root), "--feature-id", "F-001"]) == 0
    capsys.readouterr()
    assert main(["impact", "scan", "--root", str(root), "--feature-id", "F-001", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["suspects_open"] == 0


def test_impact_refresh_requires_ack_for_upstream_changed(tmp_path: Path, capsys) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "AckFlow", "--owner", "owner@example.com"]) == 0
    assert main(["impact", "refresh", "--root", str(root), "--feature-id", "F-001"]) == 0
    capsys.readouterr()

    _mutate_requirement_statement(root, "F-001", "success response", "success payload")

    assert main(["impact", "scan", "--root", str(root), "--feature-id", "F-001", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    reasons = {entry["reason"] for entry in payload["suspects"]}
    assert "changed" in reasons
    assert "upstream_changed" in reasons

    assert main(["impact", "refresh", "--root", str(root), "--feature-id", "F-001"]) == 1
    assert main(["impact", "refresh", "--root", str(root), "--feature-id", "F-001", "--ack-upstream"]) == 0
    assert main(["impact", "scan", "--root", str(root), "--feature-id", "F-001"]) == 0


def test_approve_blocks_until_impact_refresh_ack(tmp_path: Path) -> None:
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
                "ImpactApproval",
                "--status",
                "requirements_draft",
                "--owner",
                "owner@example.com",
            ]
        )
        == 0
    )
    assert main(["impact", "refresh", "--root", str(root), "--feature-id", "F-001"]) == 0
    _mutate_requirement_statement(root, "F-001", "success response", "validated response")

    assert main(["approve", "--root", str(root), "--feature-id", "F-001", "--phase", "requirements"]) == 1
    assert main(["impact", "refresh", "--root", str(root), "--feature-id", "F-001", "--ack-upstream"]) == 0
    assert main(["approve", "--root", str(root), "--feature-id", "F-001", "--phase", "requirements"]) == 0


def test_oneshot_finalize_blocks_until_impact_refresh_ack(tmp_path: Path) -> None:
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
                "ImpactFinalize",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )
    assert main(["impact", "refresh", "--root", str(root)]) == 0
    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    run_id = next((epic_dir / "runs").iterdir()).name
    scope_ids = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))["scope_feature_ids"]
    target_feature = min(scope_ids)
    _mutate_requirement_statement(root, target_feature, "success response", "success artifact")

    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 1
    assert main(["impact", "refresh", "--root", str(root), "--ack-upstream"]) == 0
    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 0


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


def _mutate_requirement_statement(root: Path, feature_id: str, old: str, new: str) -> None:
    feature_dir = next((root / "docs" / "features").glob(f"{feature_id}-*"))
    requirements_path = feature_dir / "requirements.md"
    text = requirements_path.read_text(encoding="utf-8")
    requirements_path.write_text(text.replace(old, new), encoding="utf-8")


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
                "--mode",
                "deterministic",
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


def test_epic_create_agentic_noninteractive_requires_question_pack(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    question_pack = root / "pending-questions.yaml"
    _write_epic_brief(brief_path, include_ui=True)

    rc = main(
        [
            "epic",
            "create",
            "--root",
            str(root),
            "--name",
            "AgenticMissingAnswers",
            "--owner",
            "owner@example.com",
            "--brief",
            str(brief_path),
            "--no-interactive",
            "--question-pack-out",
            str(question_pack),
        ]
    )
    assert rc == NEEDS_INPUT_EXIT_CODE
    assert question_pack.exists()
    question_payload = yaml.safe_load(question_pack.read_text(encoding="utf-8"))
    question_ids = {row["question_id"] for row in question_payload["questions"]}
    assert "Q-AGENTIC-001" in question_ids
    assert "Q-AGENTIC-002" in question_ids
    epics_text = (root / "docs" / "EPICS.md").read_text(encoding="utf-8")
    assert "| E-001 |" not in epics_text


def test_epic_create_agentic_with_answers_writes_planning_epic(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    _write_epic_brief(brief_path, include_ui=True)
    answers = root / "answers.yaml"
    answers.write_text(
        "\n".join(
            [
                "Q-AGENTIC-001: Improve activation conversion",
                "Q-AGENTIC-002: SOC2 controls apply",
                "A-AGENTIC-DECOMPOSITION: yes",
                "A-AGENTIC-COMMIT: yes",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "AgenticOnboarding",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--no-interactive",
                "--answers-file",
                str(answers),
            ]
        )
        == 0
    )

    epics_text = (root / "docs" / "EPICS.md").read_text(encoding="utf-8")
    assert "| E-001 | AgenticOnboarding | planning | F-001 |" in epics_text

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    assert (epic_dir / "research.md").exists()
    assert (epic_dir / "questions.yaml").exists()
    assert (epic_dir / "answers.yaml").exists()
    assert (epic_dir / "agentic_state.json").exists()

    oneshot = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    assert "generation_run_id" in oneshot
    assert oneshot["synthesis_quality_profile"]["minimums"]["requirements"] == 3
    assert oneshot["approval_gates"]["mode"] == "two-gate"

    rows = read_feature_rows(root / "docs" / "FEATURES.md")
    assert rows
    assert all(row.status == "tasks_draft" for row in rows)

    first_feature_dir = next((root / "docs" / "features").glob("F-001-*"))
    req_text = (first_feature_dir / "requirements.md").read_text(encoding="utf-8")
    design_text = (first_feature_dir / "design.md").read_text(encoding="utf-8")
    verification_text = (first_feature_dir / "verification.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^\s*[-*]\s*R-F001(?:\.\d{2})*-\d{3}", req_text, flags=re.MULTILINE)) >= 3
    assert "## Architecture" in design_text
    assert "## Requirement Mapping" in design_text
    assert "TBD" not in verification_text.upper()


def test_oneshot_run_transitions_planning_epic_to_implementing(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    _write_epic_brief(brief_path)
    answers = root / "answers.yaml"
    answers.write_text(
        "\n".join(
            [
                "Q-AGENTIC-001: Reduce onboarding churn",
                "Q-AGENTIC-002: ISO27001 controls apply",
                "A-AGENTIC-DECOMPOSITION: yes",
                "A-AGENTIC-COMMIT: yes",
                "",
            ]
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "AgenticLifecycle",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--no-interactive",
                "--answers-file",
                str(answers),
            ]
        )
        == 0
    )

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    epics_text = (root / "docs" / "EPICS.md").read_text(encoding="utf-8")
    assert "| E-001 | AgenticLifecycle | implementing | F-001 |" in epics_text


def test_epic_create_agentic_supports_claude_runner(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    _write_epic_brief(brief_path)
    answers = root / "answers.yaml"
    answers.write_text(
        "\n".join(
            [
                "Q-AGENTIC-001: Improve operator throughput",
                "Q-AGENTIC-002: GDPR controls apply",
                "A-AGENTIC-DECOMPOSITION: yes",
                "A-AGENTIC-COMMIT: yes",
                "",
            ]
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "ClaudeRunnerEpic",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--runner",
                "claude",
                "--no-interactive",
                "--answers-file",
                str(answers),
            ]
        )
        == 0
    )
    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    oneshot_payload = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    assert oneshot_payload["runner"] == "claude"


def test_epic_migrate_agentic_check_and_apply(tmp_path: Path) -> None:
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
                "MigrationTarget",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )

    assert main(["epic", "migrate-agentic", "--root", str(root), "--epic-id", "E-001", "--check"]) == 1
    assert main(["epic", "migrate-agentic", "--root", str(root), "--epic-id", "E-001", "--apply"]) == 0
    assert main(["epic", "migrate-agentic", "--root", str(root), "--epic-id", "E-001", "--apply"]) == 0

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    assert (epic_dir / "research.md").exists()
    oneshot_payload = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    assert oneshot_payload["synthesis_quality_profile"]["minimums"]["tasks"] == 3


def test_epic_migrate_agentic_honors_runner_and_answers_file(tmp_path: Path) -> None:
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
                "MigrationAnswersTarget",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )

    answers = root / "migration-answers.yaml"
    answers.write_text(
        "\n".join(
            [
                "Q-AGENTIC-001: Custom migration KPI",
                "Q-AGENTIC-002: Custom migration constraints",
                "",
            ]
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "epic",
                "migrate-agentic",
                "--root",
                str(root),
                "--epic-id",
                "E-001",
                "--apply",
                "--runner",
                "claude",
                "--answers-file",
                str(answers),
            ]
        )
        == 0
    )

    feature_dir = next((root / "docs" / "features").glob("F-001-*"))
    requirements = (feature_dir / "requirements.md").read_text(encoding="utf-8")
    assert "Custom migration KPI" in requirements
    assert "Custom migration constraints" in requirements

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    oneshot_payload = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    assert oneshot_payload["synthesis_quality_profile"]["migration_runner"] == "claude"


def test_epic_migrate_agentic_emits_question_pack_when_required_answers_missing(tmp_path: Path) -> None:
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
                "MigrationQuestionPackTarget",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )

    question_pack = root / "migrate-questions.yaml"
    rc = main(
        [
            "epic",
            "migrate-agentic",
            "--root",
            str(root),
            "--epic-id",
            "E-001",
            "--check",
            "--no-interactive",
            "--question-pack-out",
            str(question_pack),
        ]
    )
    assert rc == NEEDS_INPUT_EXIT_CODE
    assert question_pack.exists()
    payload = yaml.safe_load(question_pack.read_text(encoding="utf-8"))
    question_ids = {row["question_id"] for row in payload["questions"]}
    assert "Q-AGENTIC-001" in question_ids
    assert "Q-AGENTIC-002" in question_ids

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
                "--mode",
                "deterministic",
            ]
        )
        == 1
    )


def test_epic_create_passes_precomputed_stats_to_render(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief_path = root / "epic-brief.md"
    _write_epic_brief(brief_path)

    captured = {"has_stats": False}

    def render_with_stats(args):
        captured["has_stats"] = hasattr(args, "stats") and args.stats is not None
        return 0

    monkeypatch.setattr(epic_create_command.render, "run", render_with_stats)
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "EpicStatsFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )
    assert captured["has_stats"] is True


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
                "--mode",
                "deterministic",
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
                "--mode",
                "deterministic",
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


def test_oneshot_run_handles_missing_validation_binary_without_crashing(tmp_path: Path) -> None:
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
                "MissingBinaryRunFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )

    command = "definitely-not-a-real-binary-oneshot-command"
    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    payload = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    payload["repair_policy"]["max_retries_per_checkpoint"] = 0
    payload["validation_commands"] = [command]
    for checkpoint in payload["checkpoint_graph"]:
        checkpoint["validation_commands"] = [command]
    (epic_dir / "oneshot.yaml").write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    run_dir = next((epic_dir / "runs").iterdir())
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    first_checkpoint = payload["checkpoint_graph"][0]["checkpoint_id"]
    assert state["status"] == "stabilizing"
    assert state["checkpoint_status"][first_checkpoint] == "blocked_with_placeholder"
    assert "Unable to execute command" in (run_dir / "events.jsonl").read_text(encoding="utf-8")


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
                "--mode",
                "deterministic",
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


def test_oneshot_run_precreates_events_log_when_no_checkpoint_executes(tmp_path: Path) -> None:
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
                "NoProgressFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    payload = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    payload["checkpoint_graph"][0]["depends_on"] = ["C-E001-999"]
    (epic_dir / "oneshot.yaml").write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    run_dir = next((epic_dir / "runs").iterdir())
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    events_path = run_dir / "events.jsonl"
    assert state["status"] == "running"
    assert all(value == "pending" for value in state["checkpoint_status"].values())
    assert events_path.exists()
    assert events_path.read_text(encoding="utf-8") == ""


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
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )
    assert main(["impact", "refresh", "--root", str(root)]) == 0

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
                "--mode",
                "deterministic",
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


def test_oneshot_finalize_short_circuits_validation_when_blocked(tmp_path: Path, monkeypatch) -> None:
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
                "FinalizeShortCircuitFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )
    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    payload = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    payload["validation_commands"] = ["false"]
    (epic_dir / "oneshot.yaml").write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    run_id = next((epic_dir / "runs").iterdir()).name

    def should_not_run_shell(_command: str, _cwd: Path) -> tuple[int, str]:
        raise AssertionError("run_shell should not execute after finalize pre-checks already failed")

    monkeypatch.setattr(oneshot_finalize_command, "run_shell", should_not_run_shell)
    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 1


def test_oneshot_finalize_blocks_done_transition_on_finalize_validation_failure(tmp_path: Path, monkeypatch) -> None:
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
                "FinalizeGateFailureFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )
    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    oneshot_path = epic_dir / "oneshot.yaml"
    payload = yaml.safe_load(oneshot_path.read_text(encoding="utf-8"))
    payload["validation_commands"] = ["true"]
    payload.setdefault("finalize_gates", {})["required_validation_commands"] = ["false"]
    oneshot_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    run_dir = next((epic_dir / "runs").iterdir())
    run_id = run_dir.name

    def should_not_validate(_feature_dir: Path):
        raise AssertionError("traceability checks should not run after finalize validation command failure")

    monkeypatch.setattr(oneshot_finalize_command, "validate_feature_traceability", should_not_validate)
    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 1

    epics_text = (root / "docs" / "EPICS.md").read_text(encoding="utf-8")
    assert "| E-001 | FinalizeGateFailureFlow | implementing |" in epics_text
    scope_ids = set(payload["scope_feature_ids"])
    rows = read_feature_rows(root / "docs" / "FEATURES.md")
    assert all(row.status != "done" for row in rows if row.feature_id in scope_ids)


def test_oneshot_finalize_rolls_back_render_outputs_on_render_failure(tmp_path: Path, monkeypatch) -> None:
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
                "RenderRollbackFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )
    assert main(["impact", "refresh", "--root", str(root)]) == 0
    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    run_dir = next((epic_dir / "runs").iterdir())
    run_id = run_dir.name

    product_map_path = root / "docs" / "PRODUCT_MAP.md"
    traceability_path = root / "docs" / "TRACEABILITY.md"
    features_path = root / "docs" / "FEATURES.md"
    epics_path = root / "docs" / "EPICS.md"

    product_map_before = product_map_path.read_text(encoding="utf-8")
    traceability_before = traceability_path.read_text(encoding="utf-8")
    features_before = features_path.read_text(encoding="utf-8")
    epics_before = epics_path.read_text(encoding="utf-8")

    def failing_render(args):
        docs_dir = Path(args.root) / "docs"
        (docs_dir / "PRODUCT_MAP.md").write_text("CORRUPTED PRODUCT MAP\n", encoding="utf-8")
        (docs_dir / "TRACEABILITY.md").write_text("CORRUPTED TRACEABILITY\n", encoding="utf-8")
        return 1

    monkeypatch.setattr(oneshot_finalize_command.render, "run", failing_render)
    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 1

    assert product_map_path.read_text(encoding="utf-8") == product_map_before
    assert traceability_path.read_text(encoding="utf-8") == traceability_before
    assert features_path.read_text(encoding="utf-8") == features_before
    assert epics_path.read_text(encoding="utf-8") == epics_before


def test_oneshot_finalize_continues_rollback_when_one_restore_fails(tmp_path: Path, monkeypatch) -> None:
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
                "PartialRollbackFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )
    assert main(["impact", "refresh", "--root", str(root)]) == 0
    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    run_dir = next((epic_dir / "runs").iterdir())
    run_id = run_dir.name

    product_map_path = root / "docs" / "PRODUCT_MAP.md"
    traceability_path = root / "docs" / "TRACEABILITY.md"
    traceability_before = traceability_path.read_text(encoding="utf-8")

    def failing_render(args):
        docs_dir = Path(args.root) / "docs"
        (docs_dir / "PRODUCT_MAP.md").write_text("CORRUPTED PRODUCT MAP\n", encoding="utf-8")
        (docs_dir / "TRACEABILITY.md").write_text("CORRUPTED TRACEABILITY\n", encoding="utf-8")
        return 1

    original_write_text = oneshot_finalize_command.write_text
    injected_failure = {"hit": False}

    def flaky_write_text(path: Path, text: str) -> None:
        if Path(path) == product_map_path and not injected_failure["hit"]:
            injected_failure["hit"] = True
            raise OSError("simulated rollback restore failure")
        original_write_text(path, text)

    monkeypatch.setattr(oneshot_finalize_command.render, "run", failing_render)
    monkeypatch.setattr(oneshot_finalize_command, "write_text", flaky_write_text)

    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 1
    assert injected_failure["hit"] is True
    # Even when one restore operation fails, rollback should continue restoring later files.
    assert traceability_path.read_text(encoding="utf-8") == traceability_before


def test_oneshot_finalize_rolls_back_on_epic_write_failure(tmp_path: Path, monkeypatch) -> None:
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
                "WriteRollbackFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )
    assert main(["impact", "refresh", "--root", str(root)]) == 0
    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    run_dir = next((epic_dir / "runs").iterdir())
    run_id = run_dir.name

    features_path = root / "docs" / "FEATURES.md"
    epics_path = root / "docs" / "EPICS.md"
    features_before = features_path.read_text(encoding="utf-8")
    epics_before = epics_path.read_text(encoding="utf-8")

    scope_ids = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))["scope_feature_ids"]
    scope_row = next(row for row in read_feature_rows(features_path) if row.feature_id in scope_ids)
    requirements_path = (root / "docs" / scope_row.spec_path).parent / "requirements.md"
    requirements_before = requirements_path.read_text(encoding="utf-8")

    def failing_write_epics(path: Path, rows, version: str) -> None:
        path.write_text("CORRUPTED EPICS\n", encoding="utf-8")
        raise RuntimeError("forced epics write failure")

    monkeypatch.setattr(oneshot_finalize_command, "write_epic_rows", failing_write_epics)
    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 1

    assert features_path.read_text(encoding="utf-8") == features_before
    assert epics_path.read_text(encoding="utf-8") == epics_before
    assert requirements_path.read_text(encoding="utf-8") == requirements_before


def test_oneshot_finalize_rolls_back_when_run_state_is_invalid(tmp_path: Path) -> None:
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
                "StateRollbackFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )
    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    run_dir = next((epic_dir / "runs").iterdir())
    run_id = run_dir.name

    features_path = root / "docs" / "FEATURES.md"
    epics_path = root / "docs" / "EPICS.md"
    features_before = features_path.read_text(encoding="utf-8")
    epics_before = epics_path.read_text(encoding="utf-8")

    scope_ids = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))["scope_feature_ids"]
    scope_row = next(row for row in read_feature_rows(features_path) if row.feature_id in scope_ids)
    requirements_path = (root / "docs" / scope_row.spec_path).parent / "requirements.md"
    requirements_before = requirements_path.read_text(encoding="utf-8")

    (run_dir / "state.json").write_text("{invalid-json", encoding="utf-8")
    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 1

    assert features_path.read_text(encoding="utf-8") == features_before
    assert epics_path.read_text(encoding="utf-8") == epics_before
    assert requirements_path.read_text(encoding="utf-8") == requirements_before


def test_oneshot_finalize_passes_precomputed_stats_to_render(tmp_path: Path, monkeypatch) -> None:
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
                "FinalizeStatsFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )
    assert main(["impact", "refresh", "--root", str(root)]) == 0
    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    run_dir = next((epic_dir / "runs").iterdir())
    run_id = run_dir.name

    captured = {"has_stats": False}

    def render_with_stats(args):
        captured["has_stats"] = hasattr(args, "stats") and args.stats is not None
        return 0

    monkeypatch.setattr(oneshot_finalize_command.render, "run", render_with_stats)
    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 0
    assert captured["has_stats"] is True


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
                "--mode",
                "deterministic",
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
    assert main(["impact", "refresh", "--root", str(root), "--ack-upstream"]) == 0

    blockers = parse_blockers(run_dir / "blockers.md")
    assert blockers
    assert all(row["status"] != "open" for row in blockers)
    assert main(["oneshot", "finalize", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 0


def test_oneshot_resume_does_not_duplicate_open_blockers_for_retried_checkpoint(tmp_path: Path) -> None:
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
                "ResumeNoDuplicateBlockersFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
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

    blockers_before = parse_blockers(run_dir / "blockers.md")
    open_by_checkpoint_before = Counter(
        row["checkpoint_id"] for row in blockers_before if row["status"] == "open"
    )
    assert open_by_checkpoint_before

    assert main(["oneshot", "resume", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 0
    blockers_after = parse_blockers(run_dir / "blockers.md")
    open_by_checkpoint_after = Counter(row["checkpoint_id"] for row in blockers_after if row["status"] == "open")
    assert open_by_checkpoint_after == open_by_checkpoint_before


def test_oneshot_resume_processes_in_progress_checkpoint(tmp_path: Path) -> None:
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
                "ResumeInProgressFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    oneshot_path = epic_dir / "oneshot.yaml"
    payload = yaml.safe_load(oneshot_path.read_text(encoding="utf-8"))
    payload["validation_commands"] = ["true"]
    oneshot_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    run_dir = next((epic_dir / "runs").iterdir())
    run_id = run_dir.name

    checkpoint_ids = [entry["checkpoint_id"] for entry in payload["checkpoint_graph"]]
    state_path = run_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "running"
    state["checkpoint_status"] = {
        checkpoint_id: ("in_progress" if index == 0 else "pending")
        for index, checkpoint_id in enumerate(checkpoint_ids)
    }
    state["last_checkpoint"] = checkpoint_ids[0]
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    assert main(["oneshot", "resume", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 0

    resumed_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert resumed_state["status"] == "ready_to_finalize"
    assert all(value == "passed" for value in resumed_state["checkpoint_status"].values())


def test_oneshot_resume_handles_missing_validation_binary_without_crashing(tmp_path: Path) -> None:
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
                "MissingBinaryResumeFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
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

    command = "definitely-not-a-real-binary-oneshot-command"
    payload["validation_commands"] = [command]
    for checkpoint in payload["checkpoint_graph"]:
        checkpoint["validation_commands"] = [command]
    oneshot_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "resume", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 0
    resumed_state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert resumed_state["status"] == "stabilizing"
    events_text = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert '"phase": "resume"' in events_text
    assert "Unable to execute command" in events_text


def test_oneshot_run_retries_pending_checkpoints_after_late_dependency_pass(tmp_path: Path) -> None:
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
                "OutOfOrderRunFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    oneshot_path = epic_dir / "oneshot.yaml"
    payload = yaml.safe_load(oneshot_path.read_text(encoding="utf-8"))
    upstream = payload["checkpoint_graph"][0]
    downstream = payload["checkpoint_graph"][1]
    payload["checkpoint_graph"] = [downstream, upstream]
    payload["validation_commands"] = ["true"]
    for checkpoint in payload["checkpoint_graph"]:
        checkpoint["validation_commands"] = ["true"]
    oneshot_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    run_dir = next((epic_dir / "runs").iterdir())
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "ready_to_finalize"
    assert all(value == "passed" for value in state["checkpoint_status"].values())


def test_oneshot_resume_retries_pending_checkpoints_after_late_dependency_pass(tmp_path: Path) -> None:
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
                "OutOfOrderResumeFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    oneshot_path = epic_dir / "oneshot.yaml"
    payload = yaml.safe_load(oneshot_path.read_text(encoding="utf-8"))
    upstream = payload["checkpoint_graph"][0]
    downstream = payload["checkpoint_graph"][1]
    payload["checkpoint_graph"] = [downstream, upstream]
    payload["validation_commands"] = ["false"]
    for checkpoint in payload["checkpoint_graph"]:
        checkpoint["validation_commands"] = ["false"]
    oneshot_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    run_dir = next((epic_dir / "runs").iterdir())
    run_id = run_dir.name
    initial_state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert initial_state["status"] == "stabilizing"

    payload["validation_commands"] = ["true"]
    for checkpoint in payload["checkpoint_graph"]:
        checkpoint["validation_commands"] = ["true"]
    oneshot_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "resume", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 0
    resumed_state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert resumed_state["status"] == "ready_to_finalize"
    assert all(value == "passed" for value in resumed_state["checkpoint_status"].values())


def test_oneshot_resume_stops_when_status_leaves_resumable_states(tmp_path: Path, monkeypatch) -> None:
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
                "ResumeStatusGuardFlow",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )

    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    oneshot_path = epic_dir / "oneshot.yaml"
    payload = yaml.safe_load(oneshot_path.read_text(encoding="utf-8"))
    upstream = payload["checkpoint_graph"][0]
    downstream = payload["checkpoint_graph"][1]
    payload["checkpoint_graph"] = [downstream, upstream]
    payload["validation_commands"] = ["false"]
    for checkpoint in payload["checkpoint_graph"]:
        checkpoint["validation_commands"] = ["false"]
    oneshot_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    run_dir = next((epic_dir / "runs").iterdir())
    run_id = run_dir.name

    calls = {"count": 0}

    def status_mutating_process_checkpoint(**kwargs):
        calls["count"] += 1
        checkpoint_id = kwargs["checkpoint_id"]
        state = kwargs["state"]
        state["checkpoint_status"][checkpoint_id] = "passed"
        state["last_checkpoint"] = checkpoint_id
        state["status"] = "ready_to_finalize"
        return kwargs["blocker_seq"], False

    monkeypatch.setattr(oneshot_resume_command, "process_checkpoint", status_mutating_process_checkpoint)
    assert main(["oneshot", "resume", "--root", str(root), "--epic-id", "E-001", "--run-id", run_id]) == 0
    assert calls["count"] == 1
