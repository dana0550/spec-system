from __future__ import annotations

from pathlib import Path

from specctl.agentic_epic import synthesize_feature_artifacts, validate_feature_quality
from specctl.models import FeatureRow
from specctl.runner_adapter import parse_runner_json


def _feature_row(feature_id: str = "F-001") -> FeatureRow:
    return FeatureRow(
        feature_id=feature_id,
        name="Agentic Feature",
        status="tasks_draft",
        parent_id="",
        spec_path="features/F-001-agentic-feature/requirements.md",
        owner="owner@example.com",
        aliases="[]",
    )


def test_parse_runner_json_accepts_embedded_json_payload() -> None:
    output = "log line before\n{\"decomposition_nodes\": [], \"research_findings\": [], \"questions\": []}\ntrailing"
    payload, err = parse_runner_json(output)
    assert err is None
    assert payload is not None
    assert payload["decomposition_nodes"] == []


def test_synthesized_feature_meets_quality_baseline(tmp_path: Path) -> None:
    row = _feature_row()
    feature_dir = tmp_path / "features" / "F-001-agentic-feature"
    feature_dir.mkdir(parents=True)
    artifacts = synthesize_feature_artifacts(
        row=row,
        owner=row.owner,
        root_feature_name="Epic",
        findings=[{"finding_id": "FIND-001", "source": "brief", "source_type": "brief", "summary": "Brief"}],
        answers={"Q-AGENTIC-001": "Improve conversion", "Q-AGENTIC-002": "No extra constraints"},
    )
    for filename, text in artifacts.items():
        (feature_dir / filename).write_text(text, encoding="utf-8")

    issues = validate_feature_quality(feature_dir)
    assert issues == []


def test_quality_validator_accepts_canonical_child_segments(tmp_path: Path) -> None:
    feature_dir = tmp_path / "features" / "F-001.10-nested"
    feature_dir.mkdir(parents=True)
    (feature_dir / "requirements.md").write_text(
        "\n".join(
            [
                "- R-F001.10-001: WHEN valid the system MUST work.",
                "- R-F001.10-002: IF failed the system MUST recover.",
                "- R-F001.10-003: WHILE running the system SHOULD log.",
                "- S-F001.10-001: Given valid When submitted Then success.",
                "- S-F001.10-002: Given invalid When submitted Then failure.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (feature_dir / "design.md").write_text(
        "\n".join(
            [
                "## Architecture",
                "- D-F001.10-001: maps R-F001.10-001",
                "## Contracts and Data",
                "- D-F001.10-002: maps R-F001.10-002",
                "## UX Behavior",
                "- state transitions",
                "## Observability",
                "- logs",
                "## Risks and Tradeoffs",
                "- latency",
                "## Requirement Mapping",
                "- R-F001.10-001 -> D-F001.10-001",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (feature_dir / "tasks.md").write_text(
        "\n".join(
            [
                "- [ ] T-F001.10-001 do one",
                "- [ ] T-F001.10-002 do two",
                "- [ ] T-F001.10-003 do three",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (feature_dir / "verification.md").write_text(
        "\n".join(
            [
                "- S-F001.10-001: Given valid When submitted Then success.",
                "Evidence: S-F001.10-001 -> planned:test/s-f001.10-001",
                "- S-F001.10-002: Given invalid When submitted Then failure.",
                "Evidence: S-F001.10-002 -> planned:test/s-f001.10-002",
                "",
            ]
        ),
        encoding="utf-8",
    )

    issues = validate_feature_quality(feature_dir)
    assert issues == []


def test_quality_validator_flags_tbd_evidence(tmp_path: Path) -> None:
    feature_dir = tmp_path / "features" / "F-001-bad"
    feature_dir.mkdir(parents=True)
    (feature_dir / "requirements.md").write_text(
        "\n".join(
            [
                "- R-F001-001: WHEN valid the system MUST work.",
                "- R-F001-002: IF failed the system MUST recover.",
                "- R-F001-003: WHILE running the system SHOULD log.",
                "- S-F001-001: Given valid When submitted Then success.",
                "- S-F001-002: Given invalid When submitted Then failure.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (feature_dir / "design.md").write_text(
        "\n".join(
            [
                "## Architecture",
                "- D-F001-001: maps R-F001-001",
                "## Contracts and Data",
                "- D-F001-002: maps R-F001-002",
                "## UX Behavior",
                "- state transitions",
                "## Observability",
                "- logs",
                "## Risks and Tradeoffs",
                "- latency",
                "## Requirement Mapping",
                "- R-F001-001 -> D-F001-001",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (feature_dir / "tasks.md").write_text(
        "\n".join(
            [
                "- [ ] T-F001-001 do one",
                "- [ ] T-F001-002 do two",
                "- [ ] T-F001-003 do three",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (feature_dir / "verification.md").write_text(
        "\n".join(
            [
                "- S-F001-001: Given valid When submitted Then success.",
                "Evidence: S-F001-001 -> TBD",
                "- S-F001-002: Given invalid When submitted Then failure.",
                "Evidence: S-F001-002 -> planned:test/s-f001-002",
                "",
            ]
        ),
        encoding="utf-8",
    )

    issues = validate_feature_quality(feature_dir)
    assert any("TBD" in issue for issue in issues)


def test_quality_validator_rejects_non_canonical_requirement_child_segments(tmp_path: Path) -> None:
    feature_dir = tmp_path / "features" / "F-001-bad-child-segment"
    feature_dir.mkdir(parents=True)
    (feature_dir / "requirements.md").write_text(
        "\n".join(
            [
                "- R-F001.100-001: WHEN valid the system MUST work.",
                "- R-F001.100-002: IF failed the system MUST recover.",
                "- R-F001.100-003: WHILE running the system SHOULD log.",
                "- S-F001.100-001: Given valid When submitted Then success.",
                "- S-F001.100-002: Given invalid When submitted Then failure.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (feature_dir / "design.md").write_text(
        "\n".join(
            [
                "## Architecture",
                "- D-F001.100-001: maps R-F001.100-001",
                "## Contracts and Data",
                "- D-F001.100-002: maps R-F001.100-002",
                "## UX Behavior",
                "- state transitions",
                "## Observability",
                "- logs",
                "## Risks and Tradeoffs",
                "- latency",
                "## Requirement Mapping",
                "- R-F001.100-001 -> D-F001.100-001",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (feature_dir / "tasks.md").write_text(
        "\n".join(
            [
                "- [ ] T-F001.100-001 do one",
                "- [ ] T-F001.100-002 do two",
                "- [ ] T-F001.100-003 do three",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (feature_dir / "verification.md").write_text(
        "\n".join(
            [
                "- S-F001.100-001: Given valid When submitted Then success.",
                "Evidence: S-F001.100-001 -> planned:test/s-f001.100-001",
                "- S-F001.100-002: Given invalid When submitted Then failure.",
                "Evidence: S-F001.100-002 -> planned:test/s-f001.100-002",
                "",
            ]
        ),
        encoding="utf-8",
    )

    issues = validate_feature_quality(feature_dir)
    assert any(issue.startswith("requirements count") for issue in issues)
    assert any(issue.startswith("scenarios count") for issue in issues)
