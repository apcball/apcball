---
name: odoo-deploy
description: Deploy Odoo modules to DEV (Docker) or PROD (systemd) servers. Use for any deployment task — rsync + module update/restart.
---

# Odoo Deploy

Deploy one or more Odoo 17 modules to DEV or PROD servers.

## Usage

```bash
./scripts/deploy.sh <module>... [--dev|--prod|--kyld] [--test]
```

### Examples

```bash
# Deploy to DEV (Docker)
./scripts/deploy.sh buz_service_receipt --dev

# Deploy multiple modules to PROD (systemd)
./scripts/deploy.sh buz_invoice l10n_th_account_tax --prod

# Deploy to KYLD
./scripts/deploy.sh buz_custom_module --kyld

# Deploy with test on DEV (IRREVERSIBLE side effects)
./scripts/deploy.sh buz_service_receipt --dev --test
```

## Safety

- **Always confirm target server** before deploying
- `--test` runs `--test-enable` — only for DEV, has irreversible side effects
- `--prod` restarts the live service — brief downtime
- Never deploy untested changes to PROD
