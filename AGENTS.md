# AGENTS.md

## Project

~230 Odoo 17 addons for Mogen Co., Thailand. Flat in repo root — each subdirectory is one addon.

Hosted on Contabo VPS, Dockerized (`odoo:17.0` base). Postgres 16.

## Key architecture

- Custom modules: prefix `buz_` (e.g. `buz_commercial_invoice`)
- Thai localization: prefix `l10n_th_` (e.g. `l10n_th_account_tax`)
- OCA/third-party modules: no prefix — verify origin before editing
- Server-wide module: `mcp_db_resolver` (WSGI middleware, listed in `server_wide_modules`)
- MCP stack: `mcp_server` module + `mcp-odoo/mcp_odoo.py` (external client, stdio transport)
- Model namespace: `buz.<model_name>` (e.g. `buz.service.receipt`)
- XML IDs: module-prefixed (e.g. `buz_service_receipt.action_...`)

## Commands

```bash
# Deploy to DEV server
rsync -az --delete "./<module>/" root@217.216.32.33:/srv/docker/odoo/custom-addons/<module>/
ssh root@217.216.32.33 "docker exec odoo odoo -d MOG_DEV -u <module> --stop-after-init --no-http"

# Deploy to PROD server 
rsync -az --delete "./<module>/" mogenit@160.187.249.148:/srv/docker/odoo_mogen/custom-addons/<module>/
ssh mogenit@160.187.249.148 "docker exec odoo odoo -d MOG_PROD -u <module> --stop-after-init --no-http"

# Test on live DB — IRREVERSIBLE SIDE EFFECTS. Use isolated test below instead.
ssh root@217.216.32.33 "docker exec odoo odoo -d MOG_DEV -u <module> --test-enable --stop-after-init --no-http"

# Isolated test (local docker-compose with fresh Postgres)
docker compose -f docker-compose.test.yml up --abort-on-container-exit

# Lint
pip install pylint pylint-odoo
pylint --load-plugins=pylint_odoo <module>/
```

## CI flow (GitHub Actions + GitLab CI self-hosted)

`detect → lint → test → deploy`

Module detection (`detect` job):
```bash
git diff --name-only HEAD~1 HEAD | grep -oP '^[a-z][a-z0-9_]+(?=/)' | sort -u
```
For PRs: diff against base branch instead of `HEAD~1`.

- Lint uses `pylint-odoo` with `allow_failure: true`
- Tests run via `--test-enable` against the LIVE production DB container. Each module copy + update is one `docker exec` call.
- Deploy only on `main` / `Docker_Ball` branches, push events. rsync then `-u` update.
- GitLab CI deploy step is `manual` + `Docker_Ball` only.

## Module layout

Standard Odoo 17: `models/`, `views/`, `security/`, `data/`, `wizard/`, `report/`, `static/`. `__manifest__.py` defines deps and data.

## Conventions

- Multi-company: `company_id` with `_check_company=True`, `default=lambda self: self.env.company`
- Odoo 17 API only: `fields.Command` not `(0, 0, {...})` tuple syntax
- Security: `security/ir.model.access.csv` + `security/security.xml`
- DB names: `^MOG` pattern (MOG_DEV, MOG_TEST)
- Use `mail.thread` / `mail.activity.mixin` for models needing chatter

## Testing quirks

- Odoo `--test-enable` runs tests against the **actual DB** — side effects are irreversible
- Module must have `tests/` with `__init__.py` importing test classes
- No pytest, no unittest discover — Odoo test runner only
- `docker-compose.test.yml` creates isolated Postgres — **prefer this over live-DB testing**
  - Currently hardcoded to test `buz_commercial_invoice` — edit `command` for other modules
- Most modules do NOT have tests. Check for `tests/` before running.

## Never edit

`__pycache__/`, `*.pyc`, `uploads/`, `*.tar.gz`, `.env`, `.venv/`, lockfiles from other tools (`.thclaws/`, `.codewhale/`, `.deepseek/`). Module `README.*` files are Odoo app store descriptions only.

## Server paths

| Server | Host | Docker root |
|--------|------|-------------|
| DEV | `root@217.216.32.33` | `/srv/docker/odoo/` |
| PROD | `mogenit@160.187.249.148` | `/srv/docker/odoo_mogen/custom-addons` |
Container addons path: `/mnt/custom-addons` (volume mapped from `./custom-addons/`).

Config: `%DOCKER_ROOT%/config/odoo.conf`
