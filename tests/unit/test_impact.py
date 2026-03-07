from __future__ import annotations

import json
from pathlib import Path

from specctl.cli import main
from specctl.impact import build_gate_messages, impact_baseline_path, refresh_impact_baseline, scan_impact
from specctl.validators.project import lint_project


def test_scan_reports_missing_baseline_when_file_deleted(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    baseline_path = impact_baseline_path(root)
    baseline_path.unlink()

    result = scan_impact(root)
    assert result.baseline_status == "missing"
    assert result.baseline_error is not None


def test_refresh_returns_code_2_for_invalid_baseline(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "InvalidBaseline", "--owner", "owner@example.com"]) == 0
    baseline_path = impact_baseline_path(root)
    baseline_path.write_text("{not-json", encoding="utf-8")

    rc, _, suspects, refreshed = refresh_impact_baseline(root, feature_ids={"F-001"}, ack_upstream=False)
    assert rc == 2
    assert suspects == ()
    assert refreshed == 0


def test_lint_warns_for_open_impact_suspects(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "LintImpact", "--owner", "owner@example.com"]) == 0

    messages, _, _ = lint_project(root)
    assert any(message.code == "IMPACT_SUSPECT_OPEN" for message in messages)


def test_gate_message_does_not_duplicate_refresh_hint(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    impact_baseline_path(root).unlink()

    messages = build_gate_messages(root, feature_ids={"F-001"}, command_name="approve")
    assert len(messages) == 1
    assert messages[0].message.count("Run `specctl impact refresh --root .`.") == 1


def test_check_strict_fails_for_open_impact_warnings(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "StrictImpact", "--owner", "owner@example.com"]) == 0
    assert main(["render", "--root", str(root)]) == 0

    assert main(["check", "--root", str(root)]) == 0
    assert main(["check", "--root", str(root), "--strict"]) == 1


def test_scan_json_payload_contains_required_keys(tmp_path: Path, capsys) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "JsonPayload", "--owner", "owner@example.com"]) == 0
    capsys.readouterr()

    assert main(["impact", "scan", "--root", str(root), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert {"suspects_open", "features_scanned", "baseline_status", "suspects"} <= set(payload)


def test_refresh_without_ack_succeeds_when_downstream_artifacts_updated(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "DownstreamUpdate", "--owner", "owner@example.com"]) == 0
    assert main(["impact", "refresh", "--root", str(root), "--feature-id", "F-001"]) == 0

    feature_dir = next((root / "docs" / "features").glob("F-001-*"))
    requirements_path = feature_dir / "requirements.md"
    design_path = feature_dir / "design.md"
    tasks_path = feature_dir / "tasks.md"

    requirements_path.write_text(
        requirements_path.read_text(encoding="utf-8").replace("success response", "success payload"),
        encoding="utf-8",
    )
    design_path.write_text(
        design_path.read_text(encoding="utf-8").replace(
            "Implements R-F001-001 using the existing service boundary.",
            "Implements updated R-F001-001 using the existing service boundary and stricter validation.",
        ),
        encoding="utf-8",
    )
    tasks_path.write_text(
        tasks_path.read_text(encoding="utf-8").replace("Implement handler", "Implement strict handler validation"),
        encoding="utf-8",
    )

    rc, _, suspects, _ = refresh_impact_baseline(root, feature_ids={"F-001"}, ack_upstream=False)
    assert rc == 0
    assert suspects == ()
    result = scan_impact(root, feature_ids={"F-001"})
    assert result.suspects == ()


def test_refresh_noop_preserves_generated_at(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    assert main(["feature", "create", "--root", str(root), "--name", "StableBaseline", "--owner", "owner@example.com"]) == 0
    assert main(["impact", "refresh", "--root", str(root), "--feature-id", "F-001"]) == 0

    baseline_path = impact_baseline_path(root)
    first_payload = json.loads(baseline_path.read_text(encoding="utf-8"))

    rc, _, suspects, _ = refresh_impact_baseline(root, feature_ids={"F-001"}, ack_upstream=False)
    assert rc == 0
    assert suspects == ()
    second_payload = json.loads(baseline_path.read_text(encoding="utf-8"))

    assert first_payload["features"] == second_payload["features"]
    assert first_payload["generated_at"] == second_payload["generated_at"]
