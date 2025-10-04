# Spec System

![Spec System Banner](spec-system-banner.png)

A **Markdown-only product specification system** powered by OpenAI Codex (or any LLM agent) designed to keep product documentation **structured, consistent, and auto-synced** across master specs, feature specs, and product maps.

---

## 📖 Overview

This repository provides a **Single Source of Truth (SSOT)** for managing product documentation:

- **`MASTER_SPEC.md`** → product goals, principles, release scope.  
- **`FEATURES.md`** → canonical list of features (IDs, names, hierarchy, status).  
- **`PRODUCT_MAP.md`** → navigable tree view of the feature set.  
- **`features/*.md`** → individual feature specs with goals, requirements, and acceptance criteria.  
- **`DECISIONS/`** → Architecture Decision Records (ADRs).  
- **`templates/`** → reusable templates for features and ADRs.  

The system is **LLM-friendly**, using machine markers (`<!-- AUTOGEN:... -->`) so Codex or scripts can auto-update content, regenerate indices, and maintain integrity.

---

## 🚀 Key Features

- **Stable IDs, flexible names** → IDs never change; names and aliases can evolve.  
- **Propagation rules** → updates to `FEATURES.md` cascade into maps and specs.  
- **Autogen markers** → Codex auto-refreshes TOCs, children, references, and development checklists.  
- **Development Status** → requirements & acceptance criteria auto-generate checklists with traceability.  
- **Changelog support** → every file tracks changes at the bottom.  

---

## 🛠 How to Use

This system works by giving **Codex-style instructions** that trigger updates across the entire documentation set. Below are common scenarios with clear step-by-step instructions:

### 1. Bootstrapping the System
**Scenario:** Starting a new repository from scratch.  
**Instruction to Codex:**
```
Bootstrap the spec system
```
**What happens:**
- Creates the full `docs/` folder structure.  
- Generates templates and example files.  
- Initializes `MASTER_SPEC.md`, `FEATURES.md`, `PRODUCT_MAP.md`.  

---

### 2. Adding a New Feature
**Scenario:** You want to add a feature called *Clipboard Actions*.  
**Instruction to Codex:**
```
Add a new feature "Clipboard Actions" as active
```
**What happens:**
- Assigns the next available feature ID (e.g., F-007).  
- Updates `FEATURES.md`.  
- Creates a feature spec file from the template.  
- Rebuilds `PRODUCT_MAP.md` and backlinks.  
- Appends an entry to the feature’s changelog.  

---

### 3. Adding a Sub-Feature
**Scenario:** You want to add a sub-feature under F-001 (Voice Capture).  
**Instruction to Codex:**
```
Under F-001, add sub-spec "Hotword Start" as proposed
```
**What happens:**
- Creates a new ID (e.g., F-001.02).  
- Adds the sub-spec file with its own template.  
- Updates the parent’s *Children* section.  
- Rebuilds `PRODUCT_MAP.md`.  

---

### 4. Updating a Feature (Clarifications/Changes)
**Scenario:** You need to add a new requirement and acceptance criteria.  
**Instruction to Codex:**
```
Update feature "F-003":
- Add requirement R3: "Support offline caching"
- Add acceptance criterion AC3: "Given airplane mode, then dictation persists offline"
```
**What happens:**
- Updates the feature spec.  
- Refreshes development checklists automatically.  
- Appends an entry to the Changelog.  

---

### 5. Tracking Development Status
**Scenario:** Marking progress against requirements and linking to implementation work.  
**Instruction to Codex:**
```
Update feature "F-003":
- Mark R1 complete, linked to PR #123 and Test T-045
- Mark AC1 complete, linked to ENG-321
```
**What happens:**
- Updates checkboxes in the Development Status section.  
- Refreshes the traceability table with PRs, tests, tickets.  
- Appends a dated changelog entry.  

---

### 6. Recording a Decision (ADR)
**Scenario:** You decide to use SQLite for offline caching.  
**Instruction to Codex:**
```
Create ADR "Use SQLite for offline cache":
- Context: Need lightweight storage
- Decision: Adopt SQLite
- Consequences: Simplifies persistence, adds dependency
- Alternatives: Flat files, Postgres
Link ADR to feature F-003
```
**What happens:**
- Creates `DECISIONS/ADR-xxxx.md`.  
- Links ADR in the relevant feature spec.  
- Ensures backlinks are updated.  

---

### 7. Renaming a Feature Safely
**Scenario:** You want to rename "Formatting Engine" to "Text Formatter".  
**Instruction to Codex:**
```
Rename F-002 to "Text Formatter"
```
**What happens:**
- Updates the name in `FEATURES.md` (adds old name to Aliases).  
- Renames the feature spec file.  
- Rebuilds maps and backlinks.  

---

### 8. Deprecating a Feature
**Scenario:** Retiring a feature no longer in scope.  
**Instruction to Codex:**
```
Deprecate feature F-004
```
**What happens:**
- Marks the feature as `deprecated` in `FEATURES.md`.  
- Adds a banner to the spec file.  
- Removes it from active product map sections.  

---

## 🔄 Staying Up to Date

- **Instruction set versioning.** `DOCS_SYSTEM_INSTRUCTION_SET.md` now carries semantic version metadata (`MAJOR.MINOR.PATCH`) and release notes so you can see at a glance when an upgrade is available.  
- **Sync script.** Run `python scripts/sync_instruction_set.py <destination>` (where `<destination>` is the root of the repo you want to update). Use `--dry-run` to preview, `--force` to downgrade, and `--target` to override the default `docs/DOCS_SYSTEM_INSTRUCTION_SET.md` path. Example: `python scripts/sync_instruction_set.py ../product-repo --dry-run`.  
- **Codex upgrade task.** After syncing the instruction set into a working repo, run the Codex workflow `Upgrade Docs System` (Section 6.13 of the instruction set) to regenerate specs, templates, backlinks, and integrity checks with the new guidance.  
- **Changelog discipline.** Record the instruction-set upgrade in the destination repo’s changelog or ADR for traceability.  

---

## 📂 Folder Structure
```
docs/
  MASTER_SPEC.md
  FEATURES.md
  PRODUCT_MAP.md
  GLOSSARY.md
  DECISIONS/
  templates/
  features/
```

---

## ✅ Best Practices

- Always update `FEATURES.md` first.  
- Never manually edit `AUTOGEN` sections.  
- Use ADRs for architectural or design decisions.  
- Keep changelogs concise but meaningful.  
- Treat `status:` in `FEATURES.md` as canonical truth for lifecycle.  
- Note the instruction-set version and rerun `Upgrade Docs System` after pulling updates.  

---

## 📜 License

MIT License. Free to use, modify, and adapt for your projects.
