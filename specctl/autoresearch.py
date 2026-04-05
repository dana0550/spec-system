from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specctl.io_utils import write_text
from specctl.models import LintMessage
from specctl.oneshot_utils import dump_json_document, load_json_document


AUTORESEARCH_CONTEXT_FILE = "autoresearch-context.json"
AUTORESEARCH_RESULTS_HEADER = "commit\tval_bpb\tmemory_gb\tstatus\tdescription\n"
AUTORESEARCH_REQUIRED_FILES = (
    "README.md",
    "prepare.py",
    "program.md",
    "pyproject.toml",
    "train.py",
)
RUN_TAG_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class AutoresearchContext:
    repo_path: Path
    worktree_path: Path
    program_path: Path
    results_path: Path
    branch: str
    run_tag: str
    base_ref: str
    cache_dir: Path

    def to_payload(self) -> dict[str, str]:
        return {
            "repo_path": str(self.repo_path),
            "worktree_path": str(self.worktree_path),
            "program_path": str(self.program_path),
            "results_path": str(self.results_path),
            "branch": self.branch,
            "run_tag": self.run_tag,
            "base_ref": self.base_ref,
            "cache_dir": str(self.cache_dir),
        }


def validate_autoresearch_contract(payload: dict[str, Any], oneshot_path: Path) -> list[LintMessage]:
    messages: list[LintMessage] = []
    config = payload.get("autoresearch")
    if not isinstance(config, dict):
        messages.append(
            LintMessage(
                severity="ERROR",
                code="AUTORESEARCH_CONFIG_INVALID",
                message="runner 'autoresearch' requires an autoresearch object",
                path=oneshot_path,
            )
        )
        return messages

    repo_path = config.get("repo_path", "")
    if not isinstance(repo_path, str) or not repo_path.strip():
        messages.append(
            LintMessage(
                severity="ERROR",
                code="AUTORESEARCH_CONFIG_INVALID",
                message="autoresearch.repo_path must be a non-empty string",
                path=oneshot_path,
            )
        )

    run_tag = config.get("run_tag", "")
    if not isinstance(run_tag, str) or not run_tag.strip():
        messages.append(
            LintMessage(
                severity="ERROR",
                code="AUTORESEARCH_CONFIG_INVALID",
                message="autoresearch.run_tag must be a non-empty string",
                path=oneshot_path,
            )
        )
    elif not RUN_TAG_RE.match(run_tag):
        messages.append(
            LintMessage(
                severity="ERROR",
                code="AUTORESEARCH_CONFIG_INVALID",
                message="autoresearch.run_tag may only use letters, digits, dot, underscore, and dash",
                path=oneshot_path,
            )
        )

    for key in ("base_ref", "cache_dir"):
        value = config.get(key)
        if value is not None and not isinstance(value, str):
            messages.append(
                LintMessage(
                    severity="ERROR",
                    code="AUTORESEARCH_CONFIG_INVALID",
                    message=f"autoresearch.{key} must be a string when provided",
                    path=oneshot_path,
                )
            )

    has_runner_command = isinstance(payload.get("runner_command"), str) and payload.get("runner_command", "").strip()
    checkpoints = payload.get("checkpoint_graph", [])
    has_checkpoint_command = isinstance(checkpoints, list) and any(
        isinstance(checkpoint, dict)
        and isinstance(checkpoint.get("runner_command"), str)
        and checkpoint.get("runner_command", "").strip()
        for checkpoint in checkpoints
    )
    if not has_runner_command and not has_checkpoint_command:
        messages.append(
            LintMessage(
                severity="WARN",
                code="AUTORESEARCH_COMMAND_MISSING",
                message="autoresearch workspace will be prepared, but no runner_command is configured to launch an outer agent",
                path=oneshot_path,
            )
        )

    return messages


def prepare_autoresearch_context(root: Path, contract: dict[str, Any], run_dir: Path) -> dict[str, str]:
    existing = load_autoresearch_context(run_dir)
    if existing is not None:
        return existing

    config = _resolve_autoresearch_config(root, contract)
    repo_path = config["repo_path"]
    if not repo_path.exists() or not repo_path.is_dir():
        raise ValueError(f"Autoresearch repo path not found: {repo_path}")
    _verify_required_files(repo_path)

    cache_dir = config["cache_dir"]
    if not cache_dir.exists():
        raise ValueError(f"Autoresearch cache directory not found: {cache_dir}")

    base_ref = config["base_ref"] or _detect_base_ref(repo_path)
    branch = f"autoresearch/{config['run_tag']}"
    worktree_path = run_dir / "autoresearch-worktree"
    if worktree_path.exists():
        raise ValueError(f"Autoresearch worktree already exists: {worktree_path}")
    _ensure_branch_absent(repo_path, branch)
    _run_git(repo_path, ["worktree", "add", "-b", branch, str(worktree_path), base_ref])
    _verify_required_files(worktree_path)

    results_path = worktree_path / "results.tsv"
    if not results_path.exists():
        write_text(results_path, AUTORESEARCH_RESULTS_HEADER)

    context = AutoresearchContext(
        repo_path=repo_path,
        worktree_path=worktree_path,
        program_path=worktree_path / "program.md",
        results_path=results_path,
        branch=branch,
        run_tag=config["run_tag"],
        base_ref=base_ref,
        cache_dir=cache_dir,
    )
    dump_json_document(run_dir / AUTORESEARCH_CONTEXT_FILE, context.to_payload())
    return context.to_payload()


def load_autoresearch_context(run_dir: Path) -> dict[str, str] | None:
    payload, err = load_json_document(run_dir / AUTORESEARCH_CONTEXT_FILE)
    if err:
        return None
    return {key: str(value) for key, value in payload.items()}


def sync_autoresearch_program(context: dict[str, str], text: str) -> None:
    write_text(Path(context["program_path"]), text)


def expand_autoresearch_command(command: str, context: dict[str, str]) -> str:
    replacements = {
        "{autoresearch_repo_path}": context["repo_path"],
        "{autoresearch_worktree}": context["worktree_path"],
        "{autoresearch_program_path}": context["program_path"],
        "{autoresearch_branch}": context["branch"],
        "{autoresearch_results_path}": context["results_path"],
        "{autoresearch_cache_dir}": context["cache_dir"],
    }
    expanded = command
    for placeholder, value in replacements.items():
        expanded = expanded.replace(placeholder, value)
    return expanded


def build_autoresearch_program(
    *,
    epic_id: str,
    run_id: str,
    checkpoint: dict[str, Any],
    validation_commands: list[str],
    context: dict[str, str],
) -> str:
    task_ids = ", ".join(checkpoint.get("task_ids", [])) or "none"
    lines = [
        "# program.md",
        "",
        "This workspace is the exact karpathy/autoresearch repository, prepared by Spec System for a one-shot checkpoint.",
        "",
        "## Spec System Context",
        f"- Epic: {epic_id}",
        f"- Run: {run_id}",
        f"- Checkpoint: {checkpoint.get('checkpoint_id', '')}",
        f"- Feature: {checkpoint.get('feature_id', '')}",
        f"- Tasks: {task_ids}",
        "",
        "## Prepared Workspace",
        f"- Worktree: {context['worktree_path']}",
        f"- Branch: {context['branch']}",
        f"- Base ref: {context['base_ref']}",
        f"- Run tag: {context['run_tag']}",
        f"- Results file: {context['results_path']}",
        f"- Cache dir already checked: {context['cache_dir']}",
        "",
        "## Repo Contract",
        "- Read `README.md`, `prepare.py`, `train.py`, and this `program.md` before you begin.",
        "- Only edit `train.py`.",
        "- Do not modify `prepare.py`.",
        "- Do not add dependencies or change the evaluation harness.",
        "- The goal is to lower `val_bpb`.",
        "",
        "## Checkpoint Objective",
        f"- Complete checkpoint `{checkpoint.get('checkpoint_id', '')}` for feature `{checkpoint.get('feature_id', '')}`.",
        f"- Keep the branch at the best retained commit for this checkpoint.",
        "",
        "## Required Experiment Loop",
        "- If `results.tsv` only has the header or no baseline row, the first run must establish the baseline.",
        "- Commit each experimental code change before running it.",
        "- Run experiments with `uv run train.py > run.log 2>&1`.",
        "- Read `val_bpb` and `peak_vram_mb` from `run.log`.",
        "- Append one tab-separated row to `results.tsv` with commit, val_bpb, memory_gb, status, and description.",
        "- Keep only improvements in `val_bpb`; reset discarded experiments back to the prior good commit.",
        "- If a run crashes, log it as `crash` with zeroed metrics unless a trivial fix should be retried immediately.",
        "- Once experimentation begins, continue autonomously until the invoking outer runner stops you.",
        "",
        "## Output Back To Spec System",
        "- Leave `results.tsv` untracked by git.",
        "- Preserve `run.log` and the retained branch head as evidence.",
        "- Summaries should focus on the best kept experiment, discarded ideas, and any blocker that prevented progress.",
        "",
        "## Outer Validation",
    ]
    if validation_commands:
        lines.extend(f"- `{command}`" for command in validation_commands)
    else:
        lines.append("- No outer validation commands configured.")
    return "\n".join(lines) + "\n"


def _resolve_autoresearch_config(root: Path, contract: dict[str, Any]) -> dict[str, Path | str]:
    config = contract.get("autoresearch")
    if not isinstance(config, dict):
        raise ValueError("runner 'autoresearch' requires an autoresearch object in oneshot.yaml")

    repo_raw = config.get("repo_path", "")
    if not isinstance(repo_raw, str) or not repo_raw.strip():
        raise ValueError("autoresearch.repo_path must be configured")
    repo_path = Path(os.path.expanduser(repo_raw))
    if not repo_path.is_absolute():
        repo_path = (root / repo_path).resolve()

    run_tag = config.get("run_tag", "")
    if not isinstance(run_tag, str) or not run_tag.strip() or not RUN_TAG_RE.match(run_tag):
        raise ValueError("autoresearch.run_tag must be a non-empty slug-like string")

    base_ref = config.get("base_ref", "")
    if base_ref is None:
        base_ref = ""
    if not isinstance(base_ref, str):
        raise ValueError("autoresearch.base_ref must be a string when provided")

    cache_raw = config.get("cache_dir", "~/.cache/autoresearch")
    if not isinstance(cache_raw, str) or not cache_raw.strip():
        raise ValueError("autoresearch.cache_dir must be a string when provided")
    cache_dir = Path(os.path.expanduser(cache_raw)).resolve()

    return {
        "repo_path": repo_path,
        "run_tag": run_tag,
        "base_ref": base_ref.strip(),
        "cache_dir": cache_dir,
    }


def _verify_required_files(path: Path) -> None:
    missing = [name for name in AUTORESEARCH_REQUIRED_FILES if not (path / name).exists()]
    if missing:
        raise ValueError(f"Autoresearch repo missing required files: {', '.join(missing)}")


def _detect_base_ref(repo_path: Path) -> str:
    for candidate in ("master", "main"):
        if _git_ref_exists(repo_path, candidate):
            return candidate
    raise ValueError("Autoresearch repo is missing both 'master' and 'main' branches; set autoresearch.base_ref explicitly")


def _ensure_branch_absent(repo_path: Path, branch: str) -> None:
    proc = _run_git(repo_path, ["branch", "--list", branch])
    if proc.stdout.strip():
        raise ValueError(f"Autoresearch branch already exists: {branch}")


def _git_ref_exists(repo_path: Path, ref: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--verify", ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return proc.returncode == 0


def _run_git(repo_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise ValueError(stderr or f"git {' '.join(args)} failed")
    return proc
