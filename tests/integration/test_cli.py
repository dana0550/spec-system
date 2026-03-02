from __future__ import annotations

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


def test_migrate_valid_v1_fixture(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/v1_docs")
    root = copy_fixture(tmp_path, fixture)
    assert main(["migrate-v1-to-v2", "--root", str(root)]) == 0
    assert (root / "docs" / "features" / "F-001-login" / "requirements.md").exists()


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
