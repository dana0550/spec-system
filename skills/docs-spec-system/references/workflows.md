# Workflows

Use these procedures for docs-only operations. Do not run migration or code-audit workflows in this skill version.

## 1) Bootstrap Docs System

### Inputs

- Product name.
- Initial owners.
- Initial top-level feature list (optional).

### Procedure

1. Create `docs/` structure and scaffold templates.
2. Create stub `MASTER_SPEC.md`, `FEATURES.md`, `PRODUCT_MAP.md`, and `GLOSSARY.md` with required frontmatter.
3. Insert required AUTOGEN markers into scaffold templates.
4. If initial features are provided, assign IDs and seed `FEATURES.md` rows.
5. Render `PRODUCT_MAP.md` from the seeded hierarchy.
6. Run the full integrity checklist.

### Expected Mutations

- New `docs/` tree with canonical files and templates.
- Optional initial feature specs under `docs/features/`.

### Acceptance

- `FEATURES.md`, spec files, and `PRODUCT_MAP.md` are structurally consistent.
- No unresolved links or missing required frontmatter.

## 2) Add Top-Level Feature

### Inputs

- Feature name.
- Lifecycle status (`proposed`, `active`, `deprecated`).
- Owner.

### Procedure

1. Assign next top-level ID.
2. Add row to `FEATURES.md` with spec path.
3. Create feature spec from template.
4. Update `MASTER_SPEC.md` release-scope summary if relevant.
5. Rebuild map/backlinks and run integrity checks.

### Expected Mutations

- New row in `FEATURES.md`.
- New file in `docs/features/`.
- Updated `PRODUCT_MAP.md`.

### Acceptance

- New ID appears exactly once in index and exactly once in specs.

## 3) Add Sub-Feature

### Inputs

- Parent feature ID.
- Sub-feature name.
- Lifecycle status.
- Owner.

### Procedure

1. Assign next dotted child ID under the parent.
2. Add child row in `FEATURES.md` with `Parent ID`.
3. Create child spec file.
4. Refresh parent `Children` AUTOGEN section.
5. Rebuild map/backlinks and run integrity checks.

### Expected Mutations

- `FEATURES.md` contains new dotted ID row.
- Parent and child specs reflect relationship.

### Acceptance

- Child appears under correct parent in map and parent `Children` section.

## 4) Update Requirements / Acceptance Criteria / Development Status

### Inputs

- Target feature ID.
- R#/AC# additions, removals, or edits.
- Optional PR/test/ticket links.

### Procedure

1. Edit Requirements and Acceptance Criteria sections in feature spec.
2. Regenerate requirements checklist, acceptance checklist, and traceability table.
3. Apply completion states and optional evidence links.
4. Append changelog entry with date and summary.
5. Run integrity checks.

### Expected Mutations

- Feature spec content updated.
- AUTOGEN checklist blocks synced to latest R#/AC# set.

### Acceptance

- Every R#/AC# has matching checklist line and traceability row.

## 5) Rename Feature

### Inputs

- Target feature ID.
- New name.

### Procedure

1. Update name in `FEATURES.md` and append prior name to `Aliases`.
2. Rename file slug while preserving ID.
3. Update frontmatter `name` and `aliases`.
4. Rebuild links, map, and backlinks.
5. Run integrity checks.

### Expected Mutations

- `FEATURES.md` name + alias update.
- Spec file rename and frontmatter update.

### Acceptance

- ID unchanged; all references resolve; alias history retained.

## 6) Re-parent Feature

### Inputs

- Child ID.
- New parent ID.

### Procedure

1. Update `Parent ID` in `FEATURES.md`.
2. Update child spec `parent` frontmatter field.
3. Refresh affected parent/child sections.
4. Rebuild map/backlinks.
5. Validate no cycles.

### Expected Mutations

- Index and specs reflect new hierarchy.

### Acceptance

- Map and all parent/child sections match and are cycle-free.

## 7) Deprecate Feature

### Inputs

- Feature ID.
- Optional replacement IDs.

### Procedure

1. Set `status: deprecated` in `FEATURES.md` and feature frontmatter.
2. Add deprecated banner with replacement references in feature body.
3. Move entry from active map section to deprecated section.
4. Keep feature file (do not delete).
5. Run integrity checks.

### Expected Mutations

- Status updates in index/spec.
- Map reclassified entry.

### Acceptance

- Deprecated feature remains discoverable and traceable.

## 8) ADR Lifecycle

### Create ADR

1. Create `docs/DECISIONS/ADR-xxxx-<slug>.md` from template.
2. Fill context, decision, consequences, alternatives.
3. Link feature IDs in ADR frontmatter.
4. Add ADR links in related feature specs.
5. Refresh backlinks and run integrity checks.

### Update ADR Status

1. Update `status` and supersession fields.
2. Propagate supersession links to affected ADRs/features.
3. Refresh references and run integrity checks.

### Acceptance

- ADR linkage is bidirectional (ADR -> features and features -> ADR).
