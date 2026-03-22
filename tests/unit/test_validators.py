from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from specctl.cli import main
from specctl.validators.project import lint_project
from specctl.validators.requirements import validate_requirements_file


def test_ears_and_rfc_validation_passes_for_valid_requirement(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        "- R-F001-001: WHEN a request is valid the system MUST return success.\n"
        "- S-F001-001: Given valid input When submitted Then status is 200.\n",
        encoding="utf-8",
    )
    messages = validate_requirements_file(req)
    assert [m for m in messages if m.severity == "ERROR"] == []


def test_ears_validation_fails_without_trigger(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        "- R-F001-001: The system MUST return success.\n"
        "- S-F001-001: Given valid input When submitted Then status is 200.\n",
        encoding="utf-8",
    )
    messages = validate_requirements_file(req)
    codes = {m.code for m in messages}
    assert "REQ_EARS" in codes


def test_gherkin_validation_fails_without_given_when_then(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        "- R-F001-001: WHEN a request is valid the system MUST return success.\n"
        "- S-F001-001: Status is successful.\n",
        encoding="utf-8",
    )
    messages = validate_requirements_file(req)
    codes = {m.code for m in messages}
    assert "SCENARIO_GHERKIN" in codes


def test_gherkin_validation_uses_ordered_keywords_not_first_match(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        "- R-F001-001: WHEN a request is valid the system MUST return success.\n"
        "- S-F001-001: Given the THEN-processor context When submitted Then status is 200.\n",
        encoding="utf-8",
    )
    messages = validate_requirements_file(req)
    codes = {m.code for m in messages}
    assert "SCENARIO_GHERKIN" not in codes


def test_rfc_keyword_word_boundary_is_enforced(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        "- R-F001-001: WHEN a request is valid the mustard value is returned.\n"
        "- S-F001-001: Given valid input When submitted Then status is 200.\n",
        encoding="utf-8",
    )
    messages = validate_requirements_file(req)
    codes = {m.code for m in messages}
    assert "REQ_MODAL" in codes


def test_rfc_keyword_must_be_uppercase(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        "- R-F001-001: WHEN a request is valid the system must return success.\n"
        "- S-F001-001: Given valid input When submitted Then status is 200.\n",
        encoding="utf-8",
    )
    messages = validate_requirements_file(req)
    codes = {m.code for m in messages}
    assert "REQ_MODAL" in codes


def test_ears_trigger_requires_word_boundary(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        "- R-F001-001: The system MUST run elsewhere in the flow.\n"
        "- S-F001-001: Given valid input When submitted Then status is 200.\n",
        encoding="utf-8",
    )
    messages = validate_requirements_file(req)
    codes = {m.code for m in messages}
    assert "REQ_EARS" in codes


def test_project_lint_detects_missing_docs(tmp_path: Path) -> None:
    messages, _, _ = lint_project(tmp_path)
    assert any(m.code == "DOCS_MISSING" for m in messages)


def test_project_lint_allows_missing_epics_index_without_epics(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    (root / "docs" / "EPICS.md").unlink()

    messages, _, _ = lint_project(root)
    assert not any(message.code == "DOC_MISSING" and "EPICS.md" in message.message for message in messages)
    assert not any(message.code == "EPIC_INDEX_MISSING" for message in messages)


def test_project_lint_flags_missing_epics_index_when_epics_exist(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    (root / "docs" / "EPICS.md").unlink()
    (root / "docs" / "epics" / "E-001-legacy-epic").mkdir(parents=True)

    messages, _, _ = lint_project(root)
    assert any(message.code == "EPIC_INDEX_MISSING" for message in messages)


def test_project_lint_runs_epic_validation_when_features_dir_missing(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    (root / "docs" / "EPICS.md").write_text(
        "\n".join(
            [
                "---",
                "doc_type: epic_index",
                "version: 2.1.0",
                "last_synced: 2026-03-05",
                "---",
                "# Epics Index",
                "",
                "| ID | Name | Status | Root Feature ID | Epic Path | Owner | Aliases |",
                "|----|------|--------|-----------------|-----------|-------|---------|",
                "| E-001 | MissingRoot | implementing | F-999 | epics/E-001-missing-root | owner@example.com | [] |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    shutil.rmtree(root / "docs" / "features")

    messages, _, _ = lint_project(root)
    codes = {message.code for message in messages}
    assert "FEATURES_DIR_MISSING" in codes
    assert "EPIC_ROOT_FEATURE_MISSING" in codes


def test_agentic_profile_requires_research_log(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0

    brief = root / "brief.md"
    brief.write_text(
        "\n".join(
            [
                "## Vision",
                "- Improve reliability.",
                "",
                "## Outcomes",
                "- Lower incidents.",
                "",
                "## User Journeys",
                "- Operator applies policy.",
                "",
                "## Constraints",
                "- Keep APIs stable.",
                "",
                "## Non-Goals",
                "- No billing work.",
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
                "DeterministicForAgenticProfile",
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
    oneshot_path = epic_dir / "oneshot.yaml"
    payload = yaml.safe_load(oneshot_path.read_text(encoding="utf-8"))
    payload["synthesis_quality_profile"] = {
        "minimums": {"requirements": 3, "scenarios": 2, "design_decisions": 2, "tasks": 3},
        "research_log": "research.md",
        "requires_no_tbd_evidence": True,
    }
    oneshot_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    research = epic_dir / "research.md"
    if research.exists():
        research.unlink()

    messages, _, _ = lint_project(root)
    assert any(message.code == "AGENTIC_RESEARCH_LOG_MISSING" for message in messages)
