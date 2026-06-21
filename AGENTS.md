# AGENTS.md

## Project

~230 Odoo 17 addons for Mogen Co., Thailand. Flat in repo root — each subdirectory is one addon.

Hosted on Contabo VPS. DEV: Dockerized (`odoo:17.0` base). PROD: systemd service (`instance1.service`, user `odoo`, venv `/opt/instance1/odoo17-venv`). Postgres 16.

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
rsync -az --delete "./<module>/" mogenit@160.187.249.148:/opt/instance1/odoo17/custom-addons/<module>/
ssh mogenit@160.187.249.148 "sudo systemctl restart instance1"

# Test on live DB (DEV only) — IRREVERSIBLE SIDE EFFECTS. Use isolated test below instead.
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
- Tests run via `--test-enable` against the DEV Docker DB container. Each module copy + update is one `docker exec` call.
- Deploy only on `main` / `Docker_Ball` branches, push events. rsync then `sudo systemctl restart instance1`.
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

## MCP Tools (Odoo Query)

Connect to live Odoo DB via MCP. Available tools:

| Tool | Use | Example |
|------|-----|---------|
| `odoo_search(model, domain, fields?, limit?)` | ค้นหาหลาย record | `odoo_search('sale_order', [['state','=','sale']], ['name','amount_total'], 20)` |
| `odoo_read(model, id, fields?)` | อ่าน record เดียว | `odoo_read('sale_order', 16375)` |
| `odoo_create(model, values)` | สร้าง record ใหม่ | `odoo_create('partner', {name:'New Co', is_company:true})` |
| `odoo_query(endpoint, payload?)` | เรียก endpoint ใดๆ | `odoo_query('account_move_search', {domain:[['id','=',40322]]})` |
| `odoo_report(type, filters)` | รายงานยอดขาย/บัญชี | `odoo_report('sale_report', {date_from:'2026-06-01'})` |
| `odoo_company_list(fields?)` | รายชื่อบริษัททั้งหมด | `odoo_company_list()` |

### Models ที่รองรับ

`partner`, `product`, `sale_order`, `account_move`, `purchase_order`, `company`

### Tip

- ใช้ `odoo_query('sale_order_search', ...)` ตอนต้องการ fields ที่ `odoo_search` ไม่มี (เช่น `delivery_status`, `invoice_status`)
- ใช้ `odoo_query('account_move_search', ...)` เช็คสถานะการชำเงินของ invoice (`payment_state`, `amount_residual`)

## Server paths

| Server | Host | Addons root | Config | Service |
| ------ | ---- | ----------- | ------ | ------- |
| DEV | `root@217.216.32.33` | `(Docker)/srv/docker/odoo/custom-addons/` | `%DOCKER_ROOT%/config/odoo.conf` | Docker (`odoo:17.0`) |
| PROD | `mogenit@160.187.249.148` | `/opt/instance1/odoo17/custom-addons/` | `/etc/instance1.conf` | systemd (`instance1.service`, user `odoo`, venv `/opt/instance1/odoo17-venv`) |
