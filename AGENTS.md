# AGENTS.md

## Project

230+ custom Odoo 17 addons for Mogen Co., Thailand. Flat in repo root — each subdirectory is one addon. Deployed via Docker on Contabo VPS.

## Commands

```bash
# Deploy module to server via rsync + update in container
rsync -az --delete "./<module>/" root@217.216.32.33:/srv/docker/odoo/custom-addons/<module>/
ssh root@217.216.32.33 "docker exec odoo odoo -d MOG_DEV -u <module> --stop-after-init --no-http"

# Test module on live DB
ssh root@217.216.32.33 "docker exec odoo odoo -d MOG_DEV -u <module> --test-enable --stop-after-init --no-http"

# Lint locally
pip install pylint pylint-odoo && pylint --load-plugins=pylint_odoo <module>/

# Isolated test with local docker-compose
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```

## CI flow (Docker_Ball and main branches)

`detect changed modules → lint → test → deploy`

Changed modules detected via `git diff --name-only HEAD~1 HEAD`. CI runs on GitHub Actions + GitLab CI (self-hosted runner).

## Module layout

Standard Odoo 17: `models/`, `views/`, `security/`, `data/`, `wizard/`, `report/`, `static/`. `__manifest__.py` defines deps, data files, version.

## Conventions

- Model namespace: `buz.<model_name>` (e.g. `buz.service.receipt`)
- Custom Mogen modules: prefix `buz_` (e.g. `buz_commercial_invoice`)
- Thai localization: prefix `l10n_th_` (e.g. `l10n_th_account_tax`)
- Server-wide module: `mcp_db_resolver` (listed in `server_wide_modules` in odoo.conf)
- XML IDs: module-prefixed (e.g. `buz_service_receipt.action_...`)
- Multi-company: `company_id` with `_check_company=True`, `default=lambda self: self.env.company`
- DB names: pattern `^MOG` (MOG_DEV, MOG_TEST)
- Odoo 17: use `fields.Command` not `(0,0,{...})` tuple syntax
- Security: `security/ir.model.access.csv` + `security/security.xml`

## Never edit

Generated artifacts (`__pycache__/`, `*.pyc`), `uploads/`, lockfiles from other tools (`.thclaws/`, `.codewhale/`, `.deepseek/`). Module `README.*` files are description-only for Odoo app store.

## Test quirks

Tests run via Odoo `--test-enable` flag. No pytest, no unittest discover. Module must have `tests/` directory. Tests execute against actual DB — irreversible side effects on live DB possible. Use docker-compose.test.yml for isolated testing.
