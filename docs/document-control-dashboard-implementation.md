# Document Control dashboard redesign

Implemented in `buz_document_control`, version `17.0.1.2.0`.

The Document Center follows the supplied mockup: illustrated header, blue search controls, expandable filters, six KPI cards, an action table, pastel document types, three recent document cards and a department chart. Desktop uses two columns; tablet and mobile stack sections and keep wide tables inside a scrollable frame. Odoo navigation and the document viewer retain their existing styles.

KPI and department links open the records represented by their counts. Search keeps the existing 12-record pagination. Summary values use actual records and the configured review warning period. Department totals include an explicit unassigned group and aggregate named departments beyond the top five into “อื่น ๆ”. Monthly additions count active, non-archived/non-obsolete documents created in the current UTC calendar month.

## Access and compatibility

- Existing manager-only KPI/action visibility is retained. Document queries and aggregates run with the caller's ACLs and record rules. Only reading the existing review-window configuration uses elevated access.
- The document model has no `company_id`; this change does not introduce company separation or a database migration.
- Testing exposed an existing mismatch: Confidential users could see their documents but could not read their published revisions. A revision rule now mirrors the existing confidential document distribution rule. Tests verify assigned access, denied unassigned access, denied obsolete revisions and denied archived documents.
- The existing RPC signature is unchanged. Summary-only additions include department counts, month-to-date additions, drilldown domains and the configured warning window.

## Validation — 12 September 2026

- Isolated Odoo runner on PostgreSQL 16, database `MOG_TEST`: **18 tests, 0 failures, 0 errors**, process exit 0.
- Browser smoke checks: **Reader, Confidential and Manager passed**, with no browser/RPC/asset errors. Includes search, filters, PDF preview, downloads, direct URL permissions, revision workflow, native views and responsive layouts.
- Additional dashboard checks passed: all six KPI links, all section links, Edit, department/other/unassigned links, Enter-to-search, empty search, zero totals, loading, RPC error and successful retry.
- Screenshots checked at 1630, 1440, 820 and 390 pixels wide; no horizontal page overflow.
- `git diff --check` passed.

Screenshots from the isolated test fixture (sample records, not business data):

- [Desktop dashboard](/private/tmp/bdc-design-qa/manager-dashboard-final-desktop.png)
- [Tablet dashboard](/private/tmp/bdc-design-qa/manager-dashboard-final-tablet.png)
- [Mobile dashboard](/private/tmp/bdc-design-qa/manager-dashboard-final-mobile.png)
- [Empty state](/private/tmp/bdc-design-qa/dashboard-empty-data.png)
- [Loading state](/private/tmp/bdc-design-qa/dashboard-loading.png)
- [Error state](/private/tmp/bdc-design-qa/dashboard-error.png)

Repeat the isolated backend tests from the repository root:

```sh
docker compose -p bdc-design-test \
  -f docker-compose.test.yml \
  -f buz_document_control/tests/docker-compose.override.yml \
  up --abort-on-container-exit --exit-code-from odoo-test
```

The override mounts source read-only and waits for PostgreSQL readiness. Browser scripts are `ui_smoke.cjs` and `ui_dashboard_states.cjs` in the module's `tests/` directory; their usage headers describe fixture and artifact arguments. The workflow test requires a fresh database seeded with `ui_fixture.py`, restricted to names beginning with `MOG_TEST_DOCUMENT_UI_`.

No DEV or PROD deployment was performed. Local test services were stopped after validation.
