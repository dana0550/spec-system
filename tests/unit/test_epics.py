from __future__ import annotations

from pathlib import Path

import yaml

from specctl.cli import main
from specctl.commands import epic_create as epic_create_command
from specctl.oneshot_utils import needs_ui_components
from specctl.validators.project import lint_project


def _create_brief(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Epic",
                "",
                "## Vision",
                "- Improve operations.",
                "",
                "## Outcomes",
                "- Better reliability",
                "",
                "## User Journeys",
                "- Operator configures tenant",
                "",
                "## Constraints",
                "- Keep compatibility",
                "",
                "## Non-Goals",
                "- No billing",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_lint_detects_untracked_placeholder_marker(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    marker_file = root / "notes.txt"
    marker_file.write_text("TODO ONESHOT-BLOCKER:B-E001-001\n", encoding="utf-8")
    messages, _, _ = lint_project(root)
    assert any(message.code == "ONESHOT_PLACEHOLDER_UNTRACKED" for message in messages)


def test_oneshot_check_rejects_checkpoint_cycles(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief = root / "brief.md"
    _create_brief(brief)
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "CycleEpic",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )
    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    payload = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    graph = payload["checkpoint_graph"]
    graph[0]["depends_on"] = [graph[1]["checkpoint_id"]]
    graph[1]["depends_on"] = [graph[0]["checkpoint_id"]]
    payload["checkpoint_graph"] = graph
    (epic_dir / "oneshot.yaml").write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    assert main(["oneshot", "check", "--root", str(root), "--epic-id", "E-001"]) == 1


def test_oneshot_check_handles_non_list_scope_feature_ids(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    brief = root / "brief.md"
    _create_brief(brief)
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                "BadScopeType",
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )
    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    payload = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    payload["scope_feature_ids"] = 42
    (epic_dir / "oneshot.yaml").write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    assert main(["oneshot", "check", "--root", str(root), "--epic-id", "E-001"]) == 1


def test_ui_detection_uses_word_boundaries() -> None:
    assert needs_ui_components("We build resilient backend orchestration.") is False
    assert needs_ui_components("Keep deployment workflow stable.") is True
    assert needs_ui_components("This includes a dashboard workflow.") is True


def test_ui_detection_scopes_workflow_keyword_to_user_facing_sections() -> None:
    brief_constraints_only = "\n".join(
        [
            "## Vision",
            "- Improve reliability.",
            "",
            "## Outcomes",
            "- Lower incident volume.",
            "",
            "## User Journeys",
            "- Operator applies a policy.",
            "",
            "## Constraints",
            "- Preserve deployment workflow integrity.",
            "",
            "## Non-Goals",
            "- No UI redesign.",
        ]
    )
    assert needs_ui_components(brief_constraints_only) is False

    brief_user_journey = "\n".join(
        [
            "## Vision",
            "- Improve reliability.",
            "",
            "## Outcomes",
            "- Lower incident volume.",
            "",
            "## User Journeys",
            "- User completes approval workflow in dashboard.",
            "",
            "## Constraints",
            "- Preserve deployment pipeline.",
            "",
            "## Non-Goals",
            "- None.",
        ]
    )
    assert needs_ui_components(brief_user_journey) is True


def test_merge_runner_nodes_preserves_local_nodes_and_appends_runner_nodes() -> None:
    base_nodes = [
        {
            "temp_id": "N-ROOT",
            "parent_temp_id": "",
            "name": "Root",
            "node_type": "epic_root",
            "rationale": "root",
            "confidence": 0.9,
            "source_refs": ["FIND-BASE-001"],
        },
        {
            "temp_id": "N-J001",
            "parent_temp_id": "N-ROOT",
            "name": "Journey Local",
            "node_type": "journey",
            "rationale": "local",
            "confidence": 0.8,
            "source_refs": ["FIND-BASE-001"],
        },
    ]
    runner_nodes = [
        {
            "temp_id": "N-R001",
            "parent_temp_id": "N-ROOT",
            "name": "Runner Capability",
            "node_type": "capability",
            "rationale": "runner",
            "confidence": 0.7,
            "source_refs": ["FIND-RUNNER-001"],
        }
    ]

    merged = epic_create_command._merge_runner_nodes(base_nodes, runner_nodes)
    merged_ids = {node["temp_id"] for node in merged}
    assert "N-J001" in merged_ids
    assert "N-R001" in merged_ids
    assert len(merged) == 3
