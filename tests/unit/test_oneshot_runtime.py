from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from specctl.commands import oneshot_common
from specctl.commands.oneshot_common import run_shell
from specctl.commands.oneshot_runtime import (
    build_scoped_prompt,
    finalize_run_status,
    is_repo_integrity_failure,
    prompt_suffix_for_runner,
    run_validation_group,
)
from specctl.constants import ONESHOT_PLACEHOLDER_PREFIX
from specctl.oneshot_utils import append_blocker, collect_run_stats, parse_blockers, parse_task_ids, scan_placeholder_markers
from specctl.validators.oneshot import BLOCKER_ID_RE, CHECKPOINT_ID_RE


def test_run_shell_does_not_execute_shell_chain(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    rc, output = run_shell(
        'python -c "print(\'ok\')" && python -c "open(\'marker.txt\', \'w\').write(\'x\')"',
        tmp_path,
    )
    assert rc == 0
    assert "ok" in output
    assert not marker.exists()


def test_run_shell_returns_error_for_missing_binary(tmp_path: Path) -> None:
    command = "definitely-not-a-real-binary-oneshot-command"
    rc, output = run_shell(command, tmp_path)
    assert rc == 1
    assert "Unable to execute command" in output
    assert command in output


def test_validation_group_empty_commands_is_success(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    success, failed = run_validation_group(run_dir, tmp_path, "C-E001-001", [])
    assert success is True
    assert failed == []


def test_finalize_run_status_empty_checkpoint_map_is_stabilizing() -> None:
    state = {"status": "running", "checkpoint_status": {}}
    finalize_run_status(state)
    assert state["status"] == "stabilizing"


def test_repo_integrity_failure_checks_failed_commands_only() -> None:
    assert is_repo_integrity_failure(["specctl check --root ."]) is True
    assert is_repo_integrity_failure(["python -m specctl.cli check --root ."]) is True
    assert is_repo_integrity_failure(["python3 -m specctl.cli check --root ."]) is True
    assert is_repo_integrity_failure(["python -c \"import sys; sys.exit(1)\""]) is False
    assert is_repo_integrity_failure(["echo specctl check"]) is False
    assert is_repo_integrity_failure(["./run-specctl-check-suite.sh"]) is False


def test_blocker_ledger_roundtrips_pipe_characters(tmp_path: Path) -> None:
    ledger = tmp_path / "blockers.md"
    append_blocker(
        ledger,
        {
            "blocker_id": "B-E001-001",
            "checkpoint_id": "C-E001-001",
            "feature_id": "F-001",
            "task_id": "T-F001-001",
            "severity": "high",
            "type": "implementation_gap",
            "placeholder_marker": f"{ONESHOT_PLACEHOLDER_PREFIX}B-E001-001",
            "owner": "qa|ops",
            "exit_criteria": "Resolve A | B",
            "status": "open",
        },
    )
    rows = parse_blockers(ledger)
    assert len(rows) == 1
    assert rows[0]["owner"] == "qa|ops"
    assert rows[0]["exit_criteria"] == "Resolve A | B"


def test_collect_run_stats_aggregates_state_and_blockers(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_a = runs_dir / "RUN-001"
    run_b = runs_dir / "RUN-002"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    (run_a / "state.json").write_text(
        json.dumps(
            {
                "status": "running",
                "checkpoint_status": {
                    "C-E001-001": "passed",
                    "C-E001-002": "blocked_with_placeholder",
                },
            }
        ),
        encoding="utf-8",
    )
    (run_b / "state.json").write_text(
        json.dumps(
            {
                "status": "done",
                "checkpoint_status": {
                    "C-E001-003": "passed",
                    "C-E001-004": "failed_terminal",
                },
            }
        ),
        encoding="utf-8",
    )

    append_blocker(
        run_a / "blockers.md",
        {
            "blocker_id": "B-E001-001",
            "checkpoint_id": "C-E001-002",
            "feature_id": "F-001",
            "task_id": "",
            "severity": "high",
            "type": "implementation_gap",
            "placeholder_marker": f"{ONESHOT_PLACEHOLDER_PREFIX}B-E001-001",
            "owner": "owner@example.com",
            "exit_criteria": "Fix tests",
            "status": "open",
        },
    )
    append_blocker(
        run_b / "blockers.md",
        {
            "blocker_id": "B-E001-002",
            "checkpoint_id": "C-E001-004",
            "feature_id": "F-001",
            "task_id": "",
            "severity": "high",
            "type": "implementation_gap",
            "placeholder_marker": f"{ONESHOT_PLACEHOLDER_PREFIX}B-E001-002",
            "owner": "owner@example.com",
            "exit_criteria": "Fix tests",
            "status": "resolved",
        },
    )

    stats = collect_run_stats(runs_dir)
    assert stats["runs_total"] == 2
    assert stats["active_runs"] == 1
    assert stats["checkpoints_passed"] == 2
    assert stats["checkpoints_failed"] == 2
    assert stats["blockers_opened"] == 2
    assert stats["blockers_resolved"] == 1


def test_oneshot_id_regex_allows_suffixes_with_more_than_three_digits() -> None:
    assert CHECKPOINT_ID_RE.match("C-E001-001")
    assert CHECKPOINT_ID_RE.match("C-E001-1000")
    assert BLOCKER_ID_RE.match("B-E001-001")
    assert BLOCKER_ID_RE.match("B-E001-1000")


def test_scan_placeholder_markers_captures_full_blocker_id_suffix(tmp_path: Path) -> None:
    marker_file = tmp_path / "marker.txt"
    marker_file.write_text(f"TODO {ONESHOT_PLACEHOLDER_PREFIX}B-E001-1000\n", encoding="utf-8")
    hits = scan_placeholder_markers(tmp_path)
    assert len(hits) == 1
    assert hits[0][0] == marker_file
    assert hits[0][1] == 1
    assert hits[0][2] == "B-E001-1000"


def test_scan_placeholder_markers_ignores_prefix_without_blocker_id(tmp_path: Path) -> None:
    marker_file = tmp_path / "marker.txt"
    marker_file.write_text(
        f"Format: {ONESHOT_PLACEHOLDER_PREFIX}<blocker-id>\n"
        f"Example prefix only {ONESHOT_PLACEHOLDER_PREFIX}\n",
        encoding="utf-8",
    )
    hits = scan_placeholder_markers(tmp_path)
    assert hits == []


def test_parse_task_ids_accepts_variable_width_suffix() -> None:
    text = "\n".join(
        [
            "- [ ] T-F001-001 Implement baseline task",
            "- [ ] T-F001-1000 Implement long suffix task",
            "- [ ] T-F001.01-1001 Implement nested long suffix task",
        ]
    )
    ids = parse_task_ids(text)
    assert "T-F001-001" in ids
    assert "T-F001-1000" in ids
    assert "T-F001.01-1001" in ids


def test_parse_task_ids_accepts_variable_width_dotted_segments() -> None:
    text = "\n".join(
        [
            "- [ ] T-F001.1-001 single-digit segment",
            "- [ ] T-F001.010-001 triple-digit segment",
        ]
    )
    ids = parse_task_ids(text)
    assert "T-F001.1-001" in ids
    assert "T-F001.010-001" in ids


def test_run_shell_falls_back_to_sys_executable_when_python_binary_is_missing(tmp_path: Path, monkeypatch) -> None:
    seen: list[str] = []

    def fake_run(argv, **kwargs):
        seen.append(argv[0])
        if argv[0] == "python":
            raise OSError("missing python")
        return subprocess.CompletedProcess(argv, 0, "ok\n")

    monkeypatch.setattr(oneshot_common.subprocess, "run", fake_run)
    rc, output = run_shell('python -c "print(\'ok\')"', tmp_path)

    assert rc == 0
    assert output == "ok\n"
    assert seen == ["python", sys.executable]


def test_run_shell_injects_repo_pythonpath_for_specctl_module_commands(tmp_path: Path, monkeypatch) -> None:
    captured_env: dict[str, str] | None = None

    def fake_run(argv, **kwargs):
        nonlocal captured_env
        captured_env = kwargs.get("env")
        return subprocess.CompletedProcess(argv, 0, "ok\n")

    monkeypatch.setattr(oneshot_common.subprocess, "run", fake_run)
    rc, output = run_shell("python -m specctl.cli lint --root .", tmp_path)

    assert rc == 0
    assert output == "ok\n"
    assert captured_env is not None
    assert str(oneshot_common.REPO_ROOT) in captured_env["PYTHONPATH"].split(os.pathsep)


def test_prompt_suffix_for_autoresearch_uses_program_artifacts() -> None:
    assert prompt_suffix_for_runner("autoresearch") == ".program.md"
    assert prompt_suffix_for_runner("autoresearch", resume=True) == ".resume.program.md"
    assert prompt_suffix_for_runner("codex") == ".prompt.md"


def test_build_scoped_prompt_adds_autoresearch_experiment_guidance() -> None:
    prompt = build_scoped_prompt(
        "E-001",
        "RUN-001",
        {"checkpoint_id": "C-E001-001", "feature_id": "F-001", "task_ids": ["T-F001-001"]},
        "autoresearch",
        ["python -m specctl.cli check --root ."],
        {
            "repo_path": "/tmp/autoresearch",
            "worktree_path": "/tmp/autoresearch-worktree",
            "program_path": "/tmp/autoresearch-worktree/program.md",
            "results_path": "/tmp/autoresearch-worktree/results.tsv",
            "agent": "codex",
            "branch": "autoresearch/apr5",
            "run_tag": "apr5",
            "base_ref": "master",
            "cache_dir": "/tmp/autoresearch-cache",
        },
    )
    assert "exact karpathy/autoresearch repository" in prompt
    assert "- Worktree: /tmp/autoresearch-worktree" in prompt
    assert "- Branch: autoresearch/apr5" in prompt
    assert "- Outer agent: codex" in prompt
    assert "Only edit `train.py`." in prompt
    assert "Run experiments with `uv run train.py > run.log 2>&1`." in prompt
    assert "`python -m specctl.cli check --root .`" in prompt
