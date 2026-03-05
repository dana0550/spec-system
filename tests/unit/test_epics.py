from __future__ import annotations

import json
from pathlib import Path

from specctl.cli import main
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
            ]
        )
        == 0
    )
    epic_dir = next((root / "docs" / "epics").glob("E-001-*"))
    payload = json.loads((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    graph = payload["checkpoint_graph"]
    graph[0]["depends_on"] = [graph[1]["checkpoint_id"]]
    graph[1]["depends_on"] = [graph[0]["checkpoint_id"]]
    payload["checkpoint_graph"] = graph
    (epic_dir / "oneshot.yaml").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert main(["oneshot", "check", "--root", str(root), "--epic-id", "E-001"]) == 1


def test_ui_detection_uses_word_boundaries() -> None:
    assert needs_ui_components("We build resilient backend orchestration.") is False
    assert needs_ui_components("This includes a dashboard workflow.") is True
