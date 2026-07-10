# CLAUDE.md — Active development context

> Auto-maintained by "มะนาว" (Lime), AI assistant for Ball @ Mogen Co.

## Project

~230 Odoo 17 addons for Mogen Co., Thailand. Flat in repo root — each subdirectory is one addon.

### Servers

| Server | Host | Addons root | Config | Service |
|--------|------|-------------|--------|---------|
| DEV | `root@217.216.32.33` | `/srv/docker/odoo/custom-addons/` (Docker) | `%DOCKER_ROOT%/config/odoo.conf` | Docker (`odoo:17.0`) |
| PROD | `mogenit@160.187.249.148` | `/opt/instance1/odoo17/custom-addons/` | `/etc/instance1.conf` | systemd (`instance1.service`, user `odoo`, venv `/opt/instance1/odoo17-venv`) |

### CI flow

GitHub Actions + GitLab CI self-hosted (detect → lint → test → deploy).

Module detection:
```bash
git diff --name-only HEAD~1 HEAD | grep -oP '^[a-z][a-z0-9_]+(?=/)' | sort -u
```

Lint: pylint-odoo (allow_failure), Test: --test-enable against DEV DB.
Deploy: only main/Docker_Ball branches, push events.

### Key architecture

- Custom modules: prefix `buz_` (e.g. `buz_commercial_invoice`)
- Thai localization: prefix `l10n_th_` (e.g. `l10n_th_account_tax`)
- Server-wide module: `mcp_db_resolver` (WSGI middleware)
- MCP stack: `mcp_server` module + `mcp-odoo/mcp_odoo.py` (external client, stdio transport)
- Model namespace: `buz.<model_name>` (e.g. `buz.service.receipt`)
- XML IDs: module-prefixed (e.g. `buz_service_receipt.action_...`)

### Module layout

Standard Odoo 17: `models/`, `views/`, `security/`, `data/`, `wizard/`, `report/`, `static/`. `__manifest__.py` defines deps and data.

### Conventions

- Multi-company: `company_id` with `_check_company=True`, `default=lambda self: self.env.company`
- Odoo 17 API only: `fields.Command` not `(0, 0, {...})` tuple syntax
- Security: `security/ir.model.access.csv` + `security/security.xml`
- DB names: `^MOG` pattern (MOG_DEV, MOG_TEST)
- Use `mail.thread` / `mail.activity.mixin` for models needing chatter

### Testing quirks

- Odoo `--test-enable` runs tests against the **actual DB** — side effects irreversible
- Module must have `tests/` with `__init__.py` importing test classes
- No pytest, no unittest discover — Odoo test runner only
- `docker-compose.test.yml` creates isolated Postgres (edit `command` for other modules)
- Most modules do NOT have tests. Check for `tests/` before running.

### MCP Tools (Odoo Query)

Connect to live Odoo DB via MCP. Tools:
- `odoo_search`, `odoo_read`, `odoo_create`
- `odoo_query`, `odoo_report`, `odoo_company_list`

Models: partner, product, sale_order, account_move, purchase_order, company

---

## Task delegation (Claude Code & Codex CLI)

Both CLI tools available on this machine:
- **Claude Code** (`claude` v2.1.206) — Anthropic, large context, strong reasoning
- **Codex CLI** (`codex` v0.144.0) — OpenAI GPT-5.4, fast, direct

### How "มะนาว" delegates

- **Claude Code** → complex logic, multi-file refactor, testing, new module creation, wizard, complex views, anything needing broad context
- **Codex CLI** → single-point fixes, error messages, simple constraints, boilerplate, fast patches

### Hard rules

1. **มะนาว never commits or pushes without confirmation** — step before deploy
2. Deploy to DEV first, test, then PROD
3. All rsync deploys must `chmod -R +r` after sync (rsync sets 600)
4. Module version bumps are manual / confirm before commit

---

## Common commands

### Deploy DEV
```bash
rsync -az --delete "./<module>/" root@217.216.32.33:/srv/docker/odoo/custom-addons/<module>/
ssh root@217.216.32.33 "docker exec odoo odoo -d MOG_DEV -u <module> --stop-after-init --no-http"
```

### Deploy PROD
```bash
rsync -az --delete "./<module>/" mogenit@160.187.249.148:/opt/instance1/odoo17/custom-addons/<module>/
ssh mogenit@160.187.249.148 "sudo systemctl restart instance1"
```

### Test on DEV live DB (irreversible)
```bash
ssh root@217.216.32.33 "docker exec odoo odoo -d MOG_DEV -u <module> --test-enable --stop-after-init --no-http"
```

### Isolated test (local docker-compose)
```bash
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```

### Lint
```bash
pip install pylint pylint-odoo
pylint --load-plugins=pylint_odoo <module>/
```

---

## Do not edit

`__pycache__/`, `*.pyc`, `uploads/`, `*.tar.gz`, `.env`, `.venv/`, lockfiles from other tools. Module `README.*` files are Odoo app store descriptions only.

## 훑찢야 훑찢야
