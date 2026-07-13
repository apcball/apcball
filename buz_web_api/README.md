# Web API Integration for Odoo 17

This addon provisions a web integration using Odoo's native API-key storage. It does not store the secret in `web.api.integration`; Odoo stores only a hash and the generated secret is displayed once.

## Setup

1. Copy `buz_web_api` into the Odoo addons path and update the Apps list.
2. Install or upgrade `Web API Integration for Odoo`.
3. Create an internal Odoo user for the website, for example `website-warranty-integration@example.com`.
4. Open **Web API Integrations**, create `Warranty Website`, select that user, and click **Generate API Key**.
5. Copy the value shown once into the web backend secret:

```dotenv
ODOO_JSONRPC_URL=https://odoo.example.com/jsonrpc
ODOO_DB=odoo-production
ODOO_USERNAME=website-warranty-integration@example.com
ODOO_API_KEY=<the-generated-key>
```

The selected user must have the `Warranty Manager` group from `buz_warranty_management` so the existing warranty sync can create `warranty.card` records and attachments.

## Connection check

```bash
curl -i 'https://odoo.example.com/web_api/v1/health' \
  -H 'X-Odoo-Login: website-warranty-integration@example.com' \
  -H 'X-Odoo-API-Key: <the-generated-key>'
```

A valid key returns JSON containing `ok: true`, the Odoo user ID, and the database name. The endpoint never returns the key.

## Rotation

Click **Generate API Key** again to revoke the previous key with the same integration name and issue a replacement. Update the web backend secret immediately. **Revoke API Key** invalidates the current key without generating a replacement.
