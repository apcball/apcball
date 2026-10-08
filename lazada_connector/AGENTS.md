# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a collection of 230+ custom Odoo 17 addon modules for Mogen Co., Thailand. The repository is deployed on a Contabo VPS running Ubuntu 24.04 with Docker. Modules cover accounting, manufacturing (MRP), inventory, POS, sales, HR, and Thai localisation.

**Working directory on server:** `/srv/docker/odoo/custom-addons`
**Odoo config:** `/srv/docker/odoo/config/odoo.conf`
**Database names:** Match pattern `^MOG` (e.g., MOG_DEV, MOG_TEST)
**Addons path in container:** `/mnt/custom-addons`

---

## Common Commands

### Update a module on the running Odoo container
```bash
docker exec -it odoo odoo -d MOG_DEV -u <module_name> --stop-after-init --no-http
```

### Run tests for a specific module
```bash
docker exec -it odoo odoo -d MOG_DEV -u <module_name> --test-enable --stop-after-init --no-http
```

### Run the full test suite via docker-compose (isolated)
```bash
cd /srv/docker/odoo/custom-addons
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```

### Lint a module
```bash
pip install pylint pylint-odoo
pylint --load-plugins=pylint_odoo <module_name>/
```

### Copy local changes to the container
```bash
docker cp ./<module_name> odoo:/mnt/custom-addons/
```

### Rebuild Odoo image (after Dockerfile changes)
```bash
cd /srv/docker/odoo
docker compose build odoo
docker compose up -d odoo
```

### Restart Odoo container
```bash
docker restart odoo
```

---

## Module Structure

Standard Odoo 17 addon layout:

```
buz_module_name/
├── __manifest__.py          # Odoo module manifest (version, deps, data files)
├── __init__.py              # Python package init
├── models/                  # ORM model definitions (Python)
│   ├── __init__.py
│   └── <model>.py
├── views/                   # QWeb XML view definitions
├── security/                # ACL rules: ir.model.access.csv + security.xml
├── data/                    # XML data files (sequences, default data)
├── wizard/                  # TransientModel wizards (optional)
├── report/                  # QWeb report templates (optional)
└── static/                  # CSS/JS assets (optional)
```

Modules prefixed `buz_*` are custom business modules for Mogen. Other modules are either OCA community modules or third-party integrations.

---

## Architecture Notes

### Addons Path
The Odoo container uses `addons_path = /mnt/custom-addons` (set in `odoo.conf`). All 230+ modules live flat in this single directory.

### Multi-Company Aware
Modules must be multi-company compatible. Fields that need company isolation use `company_id` Many2one with `_check_company=True` and `default=lambda self: self.env.company`.

### Thai Localisation
Thai language and Thai tax (WHT, VAT) are handled by `l10n_th_*` modules. Thai fonts are installed in the Docker image (`fonts-thai-tlwg`). PDF reports render Thai text correctly.

### Server-Wide Modules
`server_wide_modules = web, mcp_db_resolver` in odoo.conf. The `mcp_db_resolver` is a custom server-wide module for MCP (Model Context Protocol) integration.

### Naming Conventions
- Model names: `buz.<model_name>` (e.g., `buz.service.receipt`)
- XML IDs: use module prefix (e.g., `buz_service_receipt.action_...`)
- Security groups: `group_buz_<module_name>_<role>`

### Database
- PostgreSQL 16 (Docker container `postgres`)
- Multiple databases: MOG_DEV, MOG_TEST (pattern `^MOG`)
- Connection config in `odoo.conf`: db_host=postgres, db_user=odoo

---

## Development Standards

### Always
- Follow Odoo 17 best practices (new API only, no old API)
- Prefer ORM over raw SQL
- Use `_sql_constraints` for DB-level uniqueness/constraints
- Use `mail.thread` and `mail.activity.mixin` for models needing chatter
- Set `company_id` default and `_check_company=True` for multi-company
- Add proper ACL in `security/ir.model.access.csv`

### Avoid
- Monkey patching unless necessary
- Hardcoded IDs (use XML IDs)
- Business logic in views (XML)
- SQL when ORM suffices
- Overriding core methods unnecessarily

### Odoo 17 Specifics
- Use `fields.Command` (not `(0, 0, {...})` tuple syntax) for O2M/M2M writes
- Use `with_company()` context for multi-company records
- `_logger` from `odoo.tools.translate` for logging
- Use `@api.onchange` sparingly; prefer computed fields with `@api.depends`

---

## Deployment

Manual deploy via Docker copy + module update:
```bash
docker cp ./<module_name> odoo:/mnt/custom-addons/
docker exec -it odoo odoo -d MOG_DEV -u <module_name> --stop-after-init --no-http
```

GitLab CI/CD (`.gitlab-ci.yml`) automates lint -> test -> deploy_staging on the `Docker_Ball` branch with a self-hosted runner.

---

## Key Files

| File | Purpose |
|------|---------|
| `/srv/docker/odoo/config/odoo.conf` | Odoo server configuration |
| `/srv/docker/odoo/docker-compose.yml` | Prod Docker Compose (Odoo + network) |
| `docker-compose.test.yml` | Isolated test environment (Postgres 16 + Odoo) |
| `Dockerfile` | Custom Odoo 17 image (Thai fonts, pythainlp, extra Python libs) |
| `requirements.txt` | Python dependencies for the custom image |
| `AGENTS.md` | Detailed AI agent instructions (Odoo standards, communication style) |
| `DEPLOYMENT_KMS.md` | Deployment runbook for KMS instance |
| `SKILL.md` | Code review skill definitions |
| `agents.json` | Agent configuration for THClaws |
