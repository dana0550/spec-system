---
doc_type: feature_requirements
feature_id: F-001
name: Karpathy Autoresearch Runner Integration
status: requirements_draft
owner: owner@example.com
last_updated: 2026-04-05
---
# Karpathy Autoresearch Runner Integration Requirements

- R-F001-001: WHEN a one-shot contract sets `runner: autoresearch`, the system MUST require an `autoresearch` configuration that identifies the exact `karpathy/autoresearch` workspace with a repo path and run tag.
- R-F001-002: WHEN `specctl oneshot run` starts an `autoresearch` checkpoint, the system MUST prepare an isolated git worktree on branch `autoresearch/<run_tag>` from the configured autoresearch repository before any runner command executes.
- R-F001-003: WHEN an `autoresearch` checkpoint is prepared, the system MUST verify the exact autoresearch repository contract by checking for `README.md`, `prepare.py`, `train.py`, `program.md`, and `pyproject.toml`, and it MUST verify that the configured cache directory exists.
- R-F001-004: WHEN an `autoresearch` checkpoint is prepared, the system MUST generate a checkpoint-scoped `program.md` that preserves Karpathy's execution rules, including baseline-first evaluation, `train.py` as the only editable file, `prepare.py` as read-only, `uv run train.py` as the experiment command, and `results.tsv` keep/discard/crash logging based on `val_bpb`.
- R-F001-005: WHEN the system prepares an `autoresearch` worktree, it MUST create `results.tsv` with the expected tab-separated header if the file is absent.
- R-F001-006: WHEN a one-shot contract sets `runner: autoresearch`, the system MUST require either `autoresearch.agent` with a supported outer agent (`codex` or `claude`) or an explicit `runner_command` override so checkpoint execution is launchable out of the box.
- R-F001-007: WHEN the system invokes an `autoresearch` runner, it MUST synthesize the correct outer-agent command for `autoresearch.agent`, and it MUST support placeholder expansion for explicit `runner_command` overrides so customized launches can still target the prepared worktree, generated `program.md`, branch name, and `results.tsv` path.
- S-F001-001: Given a oneshot contract with `runner: autoresearch` and valid autoresearch configuration When `specctl oneshot run` starts Then an isolated `autoresearch/<run_tag>` worktree and generated `program.md` are created before checkpoint execution.
- S-F001-002: Given an autoresearch contract whose repo path is missing required files or whose cache directory is absent When `specctl oneshot run` starts Then the run reports a blocking setup failure instead of pretending the checkpoint executed.
- S-F001-003: Given an autoresearch contract with `autoresearch.agent: codex` or `claude` When a checkpoint executes Then the system launches the matching outer agent inside the prepared autoresearch worktree without requiring a hand-authored `runner_command`.
- S-F001-004: Given an autoresearch contract with a runner command that uses placeholders When a checkpoint executes Then the command receives concrete worktree, branch, `program.md`, and `results.tsv` paths for the prepared autoresearch workspace.
