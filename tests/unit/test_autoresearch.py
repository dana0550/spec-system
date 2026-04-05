from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from specctl.autoresearch import (
    AUTORESEARCH_RESULTS_HEADER,
    expand_autoresearch_command,
    prepare_autoresearch_context,
    resolve_autoresearch_command,
    validate_autoresearch_contract,
)


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "master", str(path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "init"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def _create_autoresearch_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "autoresearch"
    repo.mkdir()
    (repo / "README.md").write_text("# autoresearch\n", encoding="utf-8")
    (repo / "prepare.py").write_text("print('prepare')\n", encoding="utf-8")
    (repo / "program.md").write_text("# program\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname='autoresearch'\nversion='0.1.0'\n", encoding="utf-8")
    (repo / "train.py").write_text("print('train')\n", encoding="utf-8")
    _init_git_repo(repo)

    cache_dir = tmp_path / ".cache" / "autoresearch"
    cache_dir.mkdir(parents=True)
    return repo, cache_dir


def test_validate_autoresearch_contract_requires_config(tmp_path: Path) -> None:
    messages = validate_autoresearch_contract({"runner": "autoresearch", "checkpoint_graph": []}, tmp_path / "oneshot.yaml")
    assert any(message.code == "AUTORESEARCH_CONFIG_INVALID" for message in messages)


def test_prepare_autoresearch_context_creates_worktree_and_results_header(tmp_path: Path) -> None:
    repo, cache_dir = _create_autoresearch_repo(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    contract = {
        "runner": "autoresearch",
        "autoresearch": {
            "repo_path": str(repo),
            "run_tag": "apr5",
            "cache_dir": str(cache_dir),
            "agent": "codex",
        },
    }

    context = prepare_autoresearch_context(tmp_path, contract, run_dir)

    assert Path(context["worktree_path"]).exists()
    assert Path(context["program_path"]).exists()
    assert Path(context["results_path"]).read_text(encoding="utf-8") == AUTORESEARCH_RESULTS_HEADER
    branch = subprocess.run(
        ["git", "-C", context["worktree_path"], "branch", "--show-current"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    assert branch == "autoresearch/apr5"
    assert context["agent"] == "codex"


def test_prepare_autoresearch_context_rejects_missing_cache_dir(tmp_path: Path) -> None:
    repo, cache_dir = _create_autoresearch_repo(tmp_path)
    cache_dir.rmdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    contract = {
        "runner": "autoresearch",
        "autoresearch": {
            "repo_path": str(repo),
            "run_tag": "apr5",
            "cache_dir": str(cache_dir),
            "agent": "codex",
        },
    }

    with pytest.raises(ValueError, match="cache directory not found"):
        prepare_autoresearch_context(tmp_path, contract, run_dir)


def test_prepare_autoresearch_context_rejects_missing_required_files(tmp_path: Path) -> None:
    repo, cache_dir = _create_autoresearch_repo(tmp_path)
    (repo / "train.py").unlink()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    contract = {
        "runner": "autoresearch",
        "autoresearch": {
            "repo_path": str(repo),
            "run_tag": "apr5",
            "cache_dir": str(cache_dir),
            "agent": "codex",
        },
    }

    with pytest.raises(ValueError, match="required files"):
        prepare_autoresearch_context(tmp_path, contract, run_dir)


def test_expand_autoresearch_command_replaces_placeholders() -> None:
    command = "run --cwd {autoresearch_worktree} --program {autoresearch_program_path} --branch {autoresearch_branch}"
    expanded = expand_autoresearch_command(
        command,
        {
            "repo_path": "/repo",
            "worktree_path": "/worktree",
            "program_path": "/worktree/program.md",
            "results_path": "/worktree/results.tsv",
            "agent": "codex",
            "branch": "autoresearch/apr5",
            "run_tag": "apr5",
            "base_ref": "master",
            "cache_dir": "/cache",
        },
    )
    assert "{autoresearch_" not in expanded
    assert "/worktree" in expanded
    assert "autoresearch/apr5" in expanded


def test_resolve_autoresearch_command_synthesizes_codex_launcher() -> None:
    command = resolve_autoresearch_command(
        None,
        {
            "repo_path": "/repo",
            "worktree_path": "/worktree",
            "program_path": "/worktree/program.md",
            "results_path": "/worktree/results.tsv",
            "agent": "codex",
            "branch": "autoresearch/apr5",
            "run_tag": "apr5",
            "base_ref": "master",
            "cache_dir": "/cache",
        },
    )

    assert command == 'codex exec "Read program.md and continue the loop."'


def test_validate_autoresearch_contract_requires_agent_or_runner_override(tmp_path: Path) -> None:
    messages = validate_autoresearch_contract(
        {
            "runner": "autoresearch",
            "checkpoint_graph": [],
            "autoresearch": {
                "repo_path": "/tmp/autoresearch",
                "run_tag": "apr5",
            },
        },
        tmp_path / "oneshot.yaml",
    )

    assert any(message.code == "AUTORESEARCH_LAUNCHER_MISSING" for message in messages)
