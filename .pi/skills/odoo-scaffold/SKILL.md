---
name: odoo-scaffold
description: Scaffold new Odoo 17 modules with standard structure (models, views, security, data, wizard, report, tests). Use when creating a new module from scratch.
---

# Odoo Module Scaffold

Creates a new Odoo 17 addon with full standard structure.

## Usage

```bash
./scripts/scaffold.sh <module_name> [--name "Module Display Name"] [--depends base,sale] [--model <model_name>]
```

### Examples

```bash
# Minimal — just creates structure with auto-generated __manifest__.py
./scripts/scaffold.sh buz_my_module

# With display name and dependencies
./scripts/scaffold.sh buz_my_module --name "My Module" --depends base,sale,account

# With initial model
./scripts/scaffold.sh buz_service_receipt --name "Service Receipt" --depends base,sale --model buz.service.receipt
```

## Scaffold structure

```
<module_name>/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── <model_file>.py (when --model provided)
├── views/
│   └── <model_views>.xml (when --model provided)
├── security/
│   ├── ir.model.access.csv
│   └── security.xml
├── data/
│   └── .gitkeep
├── wizard/
│   ├── __init__.py
│   └── .gitkeep
├── report/
│   ├── __init__.py
│   └── .gitkeep
└── tests/
    ├── __init__.py
    └── .gitkeep
```

## After scaffolding

1. Review `__manifest__.py` and update dependencies
2. Add fields and methods to model file
3. Update views XML with desired layout
4. Update security CSV with proper access rules
5. Register in Git and start developing

## Naming conventions

- Module name: lowercase with underscores (buz_*, l10n_th_*)
- Display name: Title Case, descriptive
- Model namespace: `buz.<model_name>` for custom modules
- XML IDs: module-prefixed
