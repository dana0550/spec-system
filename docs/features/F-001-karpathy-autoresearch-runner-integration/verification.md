---
doc_type: feature_verification
feature_id: F-001
status: requirements_draft
last_updated: 2026-04-05
---
# Karpathy Autoresearch Runner Integration Verification

- S-F001-001: Given a oneshot contract with `runner: autoresearch` and valid autoresearch configuration When `specctl oneshot run` starts Then an isolated `autoresearch/<run_tag>` worktree and generated `program.md` are created before checkpoint execution.
- S-F001-002: Given an autoresearch contract whose repo path is missing required files or whose cache directory is absent When `specctl oneshot run` starts Then the run reports a blocking setup failure instead of pretending the checkpoint executed.
- S-F001-003: Given an autoresearch contract with `autoresearch.agent: codex` or `claude` When a checkpoint executes Then the system launches the matching outer agent inside the prepared autoresearch worktree without requiring a hand-authored `runner_command`.
- S-F001-004: Given an autoresearch contract with a runner command that uses placeholders When a checkpoint executes Then the command receives concrete worktree, branch, `program.md`, and `results.tsv` paths for the prepared autoresearch workspace.
Evidence: S-F001-001 -> tests/integration/test_cli.py::test_epic_create_accepts_autoresearch_runner_and_run_emits_program_prompt
Evidence: S-F001-002 -> tests/unit/test_autoresearch.py::test_prepare_autoresearch_context_rejects_missing_cache_dir; tests/unit/test_autoresearch.py::test_prepare_autoresearch_context_rejects_missing_required_files
Evidence: S-F001-003 -> tests/integration/test_cli.py::test_epic_create_accepts_autoresearch_runner_and_run_emits_program_prompt
Evidence: S-F001-004 -> tests/unit/test_autoresearch.py::test_expand_autoresearch_command_replaces_placeholders
