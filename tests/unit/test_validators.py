from __future__ import annotations

import shutil
from pathlib import Path

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


def test_project_lint_flags_missing_epics_index_when_initialized(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["init", "--root", str(root)]) == 0
    (root / "docs" / "EPICS.md").unlink()

    messages, _, _ = lint_project(root)
    assert any(message.code == "DOC_MISSING" and "EPICS.md" in message.message for message in messages)


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
