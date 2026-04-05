---
doc_type: feature_tasks
feature_id: F-001
status: requirements_draft
last_updated: 2026-04-05
---
# Karpathy Autoresearch Runner Integration Tasks

- [ ] T-F001-001 Add oneshot contract validation for the exact `autoresearch` config block and invalid/missing repo configuration handling. (R: R-F001-001, R-F001-003, D: D-F001-001)
- [ ] T-F001-002 Implement autoresearch worktree preparation, branch creation, repo file checks, cache checks, and `results.tsv` initialization. (R: R-F001-002, R-F001-003, R-F001-005, D: D-F001-002)
- [ ] T-F001-003 Replace the generic autoresearch prompt behavior with checkpoint `program.md` generation that mirrors Karpathy's documented experiment loop and syncs into the prepared worktree. (R: R-F001-004, D: D-F001-003)
- [ ] T-F001-004 Add `runner_command` placeholder expansion and runtime metadata so an outer agent CLI can execute against the exact autoresearch worktree. (R: R-F001-006, D: D-F001-004)
- [ ] T-F001-005 Add unit/integration coverage for config validation, worktree setup, program generation, placeholder expansion, and failure paths for missing prerequisites. (R: R-F001-001, R-F001-002, R-F001-003, R-F001-004, R-F001-005, R-F001-006, D: D-F001-001, D: D-F001-002, D: D-F001-003, D: D-F001-004)
