---
doc_type: feature_design
feature_id: F-001
status: requirements_draft
last_updated: 2026-04-05
---
# Karpathy Autoresearch Runner Integration Design

- D-F001-001: Implements R-F001-001 and R-F001-002 by adding a runner-specific `autoresearch` contract block with required `repo_path` and `run_tag` fields, plus optional `base_ref` and `cache_dir` fields, so `specctl` can resolve an exact local checkout of `karpathy/autoresearch`.
- D-F001-002: Implements R-F001-002, R-F001-003, and R-F001-005 by preparing a dedicated git worktree under the one-shot run directory for `runner: autoresearch`, creating branch `autoresearch/<run_tag>`, validating the expected repo files, checking the cache directory, and seeding `results.tsv` with the exact TSV header Karpathy documents.
- D-F001-003: Implements R-F001-004 by generating checkpoint `*.program.md` artifacts for Spec System evidence and synchronizing the same content into the prepared autoresearch worktree as `program.md`, so the external agent reads the exact repo entrypoint instead of a parallel approximation.
- D-F001-004: Implements R-F001-006 by expanding explicit placeholders such as `{autoresearch_worktree}`, `{autoresearch_program_path}`, `{autoresearch_branch}`, and `{autoresearch_results_path}` inside `runner_command` before execution, allowing Spec System to stay the outer orchestrator while the actual agent CLI operates inside the exact autoresearch repo.
