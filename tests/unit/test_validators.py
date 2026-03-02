from __future__ import annotations

from pathlib import Path

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


def test_project_lint_detects_missing_docs(tmp_path: Path) -> None:
    messages, _ = lint_project(tmp_path)
    assert any(m.code == "DOCS_MISSING" for m in messages)
