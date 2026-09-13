# IT Issue Mobile — Odoo 17

## Install and configure

1. Install `buz_it_stock_mobile`. Assign **IT Issue / IT Manager** to the administrator who configures the app, and **IT Issue / IT User** to operators. These roles include Inventory User; the manager also includes Inventory Administrator. Existing Inventory access is retained.
2. Select the company in Odoo, open **IT Issue → Settings → IT Warehouse**, create its configuration, and select a warehouse and an internal source location beneath that warehouse. One configuration per company is supported. Source sublocations are included.
3. Save and click **Prepare IT Consumption Location**. This creates a company-specific `inventory` location named **เบิกใช้อุปกรณ์ IT** and an outgoing operation type. This is consumption out of company inventory, not employee custody tracking.
4. Review the destination's valuation accounts and the products' category accounting with the person responsible for inventory accounting. Configure accounts using standard Inventory screens; no account codes are guessed or created by this module. Mark **Consumption accounts reviewed / ready to use** only after this is complete. Posting follows the company's installed standard stock valuation modules.
5. On storable products, use the **IT Issue** tab to enable **Show in IT Issue** and select an IT category. Existing product images appear automatically. Set up stock and existing serials/lots using Inventory. Services and Odoo consumable-type products are excluded.
6. Maintain employees and work locations in the same company. Employees receiving equipment do not need Odoo logins. The logged-in IT operator is responsible for presenting the summary and collecting the recipient's signature.

## Workflow

Open **IT Issue** → select products and serials/lots → adjust quantities → choose recipient → **ยืนยันการเบิก** → review summary → recipient signs → **เซ็นรับและยืนยัน**.

The first confirmation saves a waiting document but does not reserve stock. Signing reserves the exact selected items and validates one picking in a single transaction. Insufficient stock or a validation wizard rolls back the whole stock operation. Partial issues and backorders are not supported. Changing a waiting document requires reconfirmation and a new signature. Completed records are immutable; returns use standard Odoo Stock Return separately.

A request UUID is kept in session storage for recovery on the same browser tab. After a network failure at signing, use **ตรวจสอบสถานะ** before retrying. The server locks the document and returns an already-completed picking on duplicate submissions. The app checks that the summary has not changed while being signed. Unsaved carts are not retained after a page reload; confirmed requests can be recovered in the same tab. The application requires an online connection and HTTPS (or localhost for development).

Ordinary operators can edit their own unfinished documents and read completed documents in allowed companies. Managers can manage all documents in allowed companies. The recipient picker returns only name, department, work location and a small avatar, without granting access to private HR records. Signatures are stored on the protected issue record, not public attachments.

Dashboard totals are separated by product unit. Only managers see estimated value, calculated as on-hand quantity × current product cost. This is not an accounting valuation report. Monthly totals use completed receipts, and the recent list follows the operator's document visibility.

## Isolated tests

From the repository root:

```sh
docker compose -p buz-it-stock-test -f docker-compose.it-stock-test.yml up --abort-on-container-exit --exit-code-from odoo
docker compose -p buz-it-stock-test -f docker-compose.it-stock-test.yml down
```

The Compose file mounts only this addon read-only, uses Postgres 16 with temporary database storage, and runs the Odoo 17 test runner against `MOG_IT_TEST`. It has no DEV/PROD connections and no published ports. Stopping its Postgres container discards test data. Never substitute a live database for this test command.

Frontend unit tests are registered in `web.qunit_suite_tests` and can be run at `/web/tests?module=buz_it_stock_mobile%20%3E%20IT%20Issue%20Mobile` on an isolated Odoo test server. The module prefix is required by Odoo's QUnit runner. Check the full receipt flow at 375, 390, 768, 1024 and 1440 pixels, including touch signing, screen rotation, serial selection, and network recovery.

With Playwright installed, run `tests/browser_acceptance.cjs`, `tests/browser_resilience.cjs`, and `tests/browser_redesign.cjs` using Node. Set `IT_TEST_URL` to the disposable localhost preview and `IT_TEST_PASSWORD` to its test account password. `IT_TEST_ARTIFACTS` controls the acceptance screenshots directory. Acceptance and resilience tests create actual receipts only in the disposable database; redesign edge cases intercept read responses to verify empty data, operator presentation, mixed units, failed images and long names. Actual authorization remains covered by the Odoo tests.

The home screen shows four equipment cards on desktop and three on mobile; **ดูทั้งหมด**, search or a category selection expands the catalog, retaining its existing pagination. Product photos come from Odoo, with category icons when absent or unavailable. The banner is a bundled SVG. Dashboard values are real; historical growth percentages are omitted, and mixed units use separate progress bars. Mobile **รายการของฉัน** filters the standard history by creator and current company. Recent receipt details open in an Odoo dialog without replacing the current cart.

Deployment is separate; use the repository's `scripts/deploy.sh` after reviewing results and authorizing the target environment.
