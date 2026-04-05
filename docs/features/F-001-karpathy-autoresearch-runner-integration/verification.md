---
doc_type: feature_verification
feature_id: F-001
status: requirements_draft
last_updated: 2026-04-05
---
# Karpathy Autoresearch Runner Integration Verification

- S-F001-001: Given a oneshot contract with `runner: autoresearch` and valid autoresearch configuration When `specctl oneshot run` starts Then an isolated `autoresearch/<run_tag>` worktree and generated `program.md` are created before checkpoint execution.
- S-F001-002: Given an autoresearch contract whose repo path is missing required files or whose cache directory is absent When `specctl oneshot run` starts Then the run reports a blocking setup failure instead of pretending the checkpoint executed.
- S-F001-003: Given an autoresearch contract with a runner command that uses placeholders When a checkpoint executes Then the command receives concrete worktree, branch, `program.md`, and `results.tsv` paths for the prepared autoresearch workspace.
Evidence: S-F001-001 -> TBD
Evidence: S-F001-002 -> TBD
Evidence: S-F001-003 -> TBD
