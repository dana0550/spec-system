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

### Bootstrap the system
```
Ask Codex: "Bootstrap the spec system."
```
This will create the folder structure, templates, and initial docs.

### Add a new feature
```
Add a new feature "Clipboard Actions" as active
```
Codex will:
- Assign the next feature ID.  
- Update `FEATURES.md`.  
- Create a feature spec file from the template.  
- Rebuild the product map & backlinks.  
- Append to the changelog.  

### Update development status
```
Update feature "F-003":
- Mark R1 complete, linked to PR #123
- Mark AC1 complete, linked to Test T-045
```
Codex will refresh checklists, update traceability, and append to the changelog.

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

---

## 📜 License

MIT License. Free to use, modify, and adapt for your projects.
