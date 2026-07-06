# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a collection of 230+ custom Odoo 17 addon modules for Mogen Co., Thailand. Each subdirectory in the repo root is one addon. Modules cover accounting, manufacturing (MRP), inventory, POS, sales, HR, and Thai localisation. Postgres 16.

Two environments:

- **DEV** (`root@217.216.32.33`): Dockerized, `odoo:17.0` base. Addons root `/srv/docker/odoo/custom-addons/`, config `/srv/docker/odoo/config/odoo.conf`, addons path in container `/mnt/custom-addons`.
- **PROD** (`mogenit@160.187.249.148`): systemd service `instance1.service` (user `odoo`, venv `/opt/instance1/odoo17-venv`). Addons root `/opt/instance1/odoo17/custom-addons/`, config `/etc/instance1.conf`.

**Database names:** Match pattern `^MOG` (e.g., MOG_DEV, MOG_TEST).

---

## Common Commands

### Deploy to DEV server
```bash
rsync -az --delete "./<module>/" root@217.216.32.33:/srv/docker/odoo/custom-addons/<module>/
ssh root@217.216.32.33 "docker exec odoo odoo -d MOG_DEV -u <module> --stop-after-init --no-http"
```

### Deploy to PROD server
```bash
rsync -az --delete "./<module>/" mogenit@160.187.249.148:/opt/instance1/odoo17/custom-addons/<module>/
ssh mogenit@160.187.249.148 "sudo systemctl restart instance1"
```

### Copy local changes to the container (DEV, quick)
```bash
docker cp ./<module_name> odoo:/mnt/custom-addons/
```

### Update a module on the running Odoo container
```bash
docker exec -it odoo odoo -d MOG_DEV -u <module_name> --stop-after-init --no-http
```

### Run tests for a specific module
⚠️ `--test-enable` runs against the **actual DB** — side effects are irreversible. Prefer isolated test below.
```bash
docker exec -it odoo odoo -d MOG_DEV -u <module_name> --test-enable --stop-after-init --no-http
```

### Run the full test suite via docker-compose (isolated, fresh Postgres)
```bash
cd /srv/docker/odoo/custom-addons
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```
Note: `docker-compose.test.yml` is currently hardcoded to test `buz_commercial_invoice` — edit `command` for other modules.

### Lint a module
```bash
pip install pylint pylint-odoo
pylint --load-plugins=pylint_odoo <module_name>/
```

### Rebuild Odoo image (after Dockerfile changes, DEV)
```bash
cd /srv/docker/odoo
docker compose build odoo
docker compose up -d odoo
```

### Restart Odoo container (DEV)
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

### Module Prefixes
- Custom business modules: `buz_*` (e.g., `buz_commercial_invoice`) — safe to edit.
- Thai localisation: `l10n_th_*` (e.g., `l10n_th_account_tax`).
- OCA / third-party modules: no prefix — **verify origin before editing**.

### Addons Path
The Odoo container uses `addons_path = /mnt/custom-addons` (set in `odoo.conf`). All 230+ modules live flat in this single directory.

### Multi-Company Aware
Modules must be multi-company compatible. Fields that need company isolation use `company_id` Many2one with `_check_company=True` and `default=lambda self: self.env.company`.

### Thai Localisation
Thai language and Thai tax (WHT, VAT) are handled by `l10n_th_*` modules. Thai fonts are installed in the Docker image (`fonts-thai-tlwg`). PDF reports render Thai text correctly.

### MCP Integration
- Server-wide module: `mcp_db_resolver` (WSGI middleware, listed in `server_wide_modules` in `odoo.conf`).
- MCP stack: `mcp_server` module + external client `mcp-odoo/mcp_odoo.py` (stdio transport). See MCP Tools section below.

### Naming Conventions
- Model namespace: `buz.<model_name>` (e.g., `buz.service.receipt`)
- XML IDs: module-prefixed (e.g., `buz_service_receipt.action_...`)
- Security groups: `group_buz_<module_name>_<role>`

### Database
- PostgreSQL 16 (DEV: Docker container `postgres`; PROD: native)
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

Manual deploy via rsync (see Common Commands above). Two CI pipelines:

- **GitHub Actions + GitLab CI (self-hosted)**: `detect → lint → test → deploy`.
- Module detection (`detect` job):
  ```bash
  git diff --name-only HEAD~1 HEAD | grep -oP '^[a-z][a-z0-9_]+(?=/)' | sort -u
  ```
  For PRs: diff against base branch instead of `HEAD~1`.
- Lint uses `pylint-odoo` with `allow_failure: true`.
- Tests run via `--test-enable` against the DEV Docker DB container; each module copy + update is one `docker exec`.
- Deploy only on `main` / `Docker_Ball` branches, push events. rsync then `sudo systemctl restart instance1` (PROD).
- GitLab CI deploy step is `manual` + `Docker_Ball` only.

---

## Testing Quirks

- Odoo `--test-enable` runs tests against the **actual DB** — side effects are irreversible.
- Module must have `tests/` with `__init__.py` importing test classes.
- No pytest, no unittest discover — Odoo test runner only.
- `docker-compose.test.yml` creates an isolated Postgres — **prefer this over live-DB testing**.
- Most modules do NOT have tests. Check for `tests/` before running.

---

## Never Edit

`__pycache__/`, `*.pyc`, `uploads/`, `*.tar.gz`, `.env`, `.venv/`, and lockfiles from other tools (`.thclaws/`, `.codewhale/`, `.deepseek/`). Module `README.*` files are Odoo app-store descriptions only.

---

## MCP Tools (Odoo Query)

Connect to live Odoo DB via MCP. Available tools:

| Tool | Use | Example |
|------|-----|---------|
| `odoo_search(model, domain, fields?, limit?)` | Search many records | `odoo_search('sale_order', [['state','=','sale']], ['name','amount_total'], 20)` |
| `odoo_read(model, id, fields?)` | Read single record | `odoo_read('sale_order', 16375)` |
| `odoo_create(model, values)` | Create record | `odoo_create('partner', {name:'New Co', is_company:true})` |
| `odoo_query(endpoint, payload?)` | Call any endpoint | `odoo_query('account_move_search', {domain:[['id','=',40322]]})` |
| `odoo_report(type, filters)` | Sales/accounting report | `odoo_report('sale_report', {date_from:'2026-06-01'})` |
| `odoo_company_list(fields?)` | List all companies | `odoo_company_list()` |

Supported models: `partner`, `product`, `sale_order`, `account_move`, `purchase_order`, `company`.

Tips:
- Use `odoo_query('sale_order_search', ...)` for fields `odoo_search` lacks (e.g., `delivery_status`, `invoice_status`).
- Use `odoo_query('account_move_search', ...)` to check invoice payment state (`payment_state`, `amount_residual`).

---

## Server Paths

| Server | Host | Addons root | Config | Service |
| ------ | ---- | ----------- | ------ | ------- |
| DEV | `root@217.216.32.33` | `/srv/docker/odoo/custom-addons/` | `/srv/docker/odoo/config/odoo.conf` | Docker (`odoo:17.0`) |
| PROD | `mogenit@160.187.249.148` | `/opt/instance1/odoo17/custom-addons/` | `/etc/instance1.conf` | systemd (`instance1.service`, user `odoo`, venv `/opt/instance1/odoo17-venv`) |

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
