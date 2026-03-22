from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from specctl.commands import codex_check


def test_codex_check_fails_for_malformed_toml(tmp_path: Path, capsys) -> None:
    root = tmp_path / "workspace"
    _write_codex_required_files(root)
    (root / ".codex" / "config.toml").write_text("[profiles.spec-agentic\nmodel = 'gpt-5.4'\n", encoding="utf-8")

    rc = codex_check.run(Namespace(root=str(root), json=True))
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert any("parse error" in item for item in payload["missing"])


def test_codex_check_fails_when_profile_key_missing(tmp_path: Path, capsys) -> None:
    root = tmp_path / "workspace"
    _write_codex_required_files(root)
    (root / ".codex" / "config.toml").write_text(
        "\n".join(
            [
                "[profiles.spec-agentic]",
                "model = 'gpt-5.4'",
                "model_reasoning_effort = 'high'",
                "sandbox_mode = 'workspace-write'",
                "approval_policy = 'on-request'",
                "web_search = 'cached'",
                "",
                "[profiles.spec-ci]",
                "model = 'gpt-5.4-mini'",
                "model_reasoning_effort = 'medium'",
                "sandbox_mode = 'workspace-write'",
                "approval_policy = 'never'",
                "web_search = 'disabled'",
                "",
                "[profiles.spec-review]",
                "model = 'gpt-5.4'",
                "model_reasoning_effort = 'medium'",
                "sandbox_mode = 'read-only'",
                "approval_policy = 'never'",
                "",
            ]
        ),
        encoding="utf-8",
    )

    rc = codex_check.run(Namespace(root=str(root), json=True))
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert any("profiles.spec-review" in item and "web_search" in item for item in payload["missing"])


def test_codex_check_passes_for_valid_config(tmp_path: Path, capsys) -> None:
    root = tmp_path / "workspace"
    _write_codex_required_files(root)
    (root / ".codex" / "config.toml").write_text(
        "\n".join(
            [
                "[profiles.spec-agentic]",
                "model = 'gpt-5.4'",
                "model_reasoning_effort = 'high'",
                "sandbox_mode = 'workspace-write'",
                "approval_policy = 'on-request'",
                "web_search = 'cached'",
                "",
                "[profiles.spec-ci]",
                "model = 'gpt-5.4-mini'",
                "model_reasoning_effort = 'medium'",
                "sandbox_mode = 'workspace-write'",
                "approval_policy = 'never'",
                "web_search = 'disabled'",
                "",
                "[profiles.spec-review]",
                "model = 'gpt-5.4'",
                "model_reasoning_effort = 'medium'",
                "sandbox_mode = 'read-only'",
                "approval_policy = 'never'",
                "web_search = 'cached'",
                "",
            ]
        ),
        encoding="utf-8",
    )

    rc = codex_check.run(Namespace(root=str(root), json=True))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["missing"] == []


def _write_codex_required_files(root: Path) -> None:
    files = [
        "AGENTS.md",
        ".codex/config.toml",
        "scripts/codex/worktree-setup.sh",
        "scripts/codex/project-actions.sh",
        "assets/codex/automations/spec-quality-check.md",
        "assets/codex/automations/migration-audit.md",
    ]
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel == "AGENTS.md":
            path.write_text("# AGENTS\n\n## Review guidelines\n", encoding="utf-8")
        else:
            path.write_text("placeholder\n", encoding="utf-8")
