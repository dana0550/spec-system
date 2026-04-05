---
doc_type: feature_design
feature_id: F-001
status: requirements_draft
last_updated: 2026-04-05
---
# Karpathy Autoresearch Runner Integration Design

- D-F001-001: Implements R-F001-001, R-F001-002, and R-F001-006 by adding a runner-specific `autoresearch` contract block with required `repo_path` and `run_tag` fields, plus an `agent` launcher field and optional `base_ref` and `cache_dir` fields, so `specctl` can resolve an exact local checkout of `karpathy/autoresearch` and decide how to launch the outer agent.
- D-F001-002: Implements R-F001-002, R-F001-003, and R-F001-005 by preparing a dedicated git worktree under the one-shot run directory for `runner: autoresearch`, creating branch `autoresearch/<run_tag>`, validating the expected repo files, checking the cache directory, and seeding `results.tsv` with the exact TSV header Karpathy documents.
- D-F001-003: Implements R-F001-004 by generating checkpoint `*.program.md` artifacts for Spec System evidence and synchronizing the same content into the prepared autoresearch worktree as `program.md`, so the external agent reads the exact repo entrypoint instead of a parallel approximation.
- D-F001-004: Implements R-F001-006 and R-F001-007 by synthesizing concrete launcher commands for supported outer agents (`codex exec ...` and `claude -p ...`) when `autoresearch.agent` is configured, so `runner: autoresearch` is executable without a hand-authored shell command.
- D-F001-005: Implements R-F001-007 by expanding explicit placeholders such as `{autoresearch_worktree}`, `{autoresearch_program_path}`, `{autoresearch_branch}`, and `{autoresearch_results_path}` inside `runner_command` overrides before execution, preserving a customization escape hatch while Spec System remains the outer orchestrator.
