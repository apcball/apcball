---
description: Odoo 17 project conventions for Mogen Co. buz_ and l10n_th_ modules. Use when starting a new task to set context.
argument-hint: "[task description]"
---

# Odoo 17 Project Conventions

Project: ~230 Odoo 17 addons for Mogen Co., Thailand

## Module prefixes
- Custom modules: `buz_` — commercial, service, inventory extensions
- Thai localization: `l10n_th_` — tax, accounting, reporting
- OCA/third-party: no prefix — verify origin before editing

## Model namespace
- `buz.<model_name>` (e.g. `buz.service.receipt`, `buz.commercial.invoice`)
- Always use `_inherit` not `_inherit +=` for extending existing models

## Code patterns (Odoo 17 only)
- Use `fields.Command.create/update/delete` — NOT tuple syntax `(0, 0, ...)`
- Multi-company: `company_id` with `_check_company=True`, `default=lambda self: self.env.company`
- Chatter: `_inherit = ['mail.thread', 'mail.activity.mixin']`
- Security: `security/ir.model.access.csv` + `security/security.xml`
- XML IDs: module-prefixed (e.g. `buz_service_receipt.action_...`)

## Module structure
```
__manifest__.py / __init__.py / models/ / views/ / security/ / data/ / wizard/ / report/ / tests/ / static/
```

## Servers
- DEV: Docker (root@217.216.32.33), DB: MOG_DEV
- PROD: systemd (mogenit@160.187.249.148), service: instance1
- KYLD: Docker (mogenit@119.13.29.46), DB: KYLD_PROD

## Testing
- Odoo test runner only (no pytest)
- Prefer `docker compose -f docker-compose.test.yml up --abort-on-container-exit`
- `--test-enable` on DEV has irreversible side effects — warn first
