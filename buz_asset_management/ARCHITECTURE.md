# ARCHITECTURE.md --- BUZ Asset Management for Odoo 17

**Module:** `buz_asset_management`\
**Target:** Odoo 17.0\
**Style:** Modular Odoo addon; operational asset subledger + accounting
integration adapter.

## 1. Architectural principles

1.  `account.move` / `account.move.line` are the source of truth for
    posted accounting.
2.  BUZ asset records are the source of truth for physical identity,
    custody, location, operational status and history.
3.  Do not maintain independently editable GL balances on `buz.asset`.
4.  Reuse native Odoo asset depreciation if the deployed edition/addons
    provide a compatible implementation. Do not assume availability from
    version number alone.
5.  If native asset accounting is unavailable, implement a custom
    backend behind a stable adapter interface.
6.  All accounting writes go through ORM and standard accounting
    validation.
7.  Posted moves are immutable from this module; corrections use
    reversal/adjustment.
8.  Scheduled actions are idempotent and safe to retry.
9.  Multi-company consistency is enforced at model, record-rule and
    accounting validation levels.
10. Operational modules must not depend on accounting implementation
    details.

## 2. Deployment discovery gate

Before coding integration, inspect: - Odoo edition and exact 17.0
build. - Installed modules and availability of `account_asset`. - Actual
model names and fields in the deployed asset implementation. - Existing
custom asset modules and `account.move` customizations. - Accounting
Date Policy / lock-date customizations. - Company currency, chart of
accounts, depreciation journals and analytic setup.

Example Odoo shell discovery (adapt paths and environment):

``` python
env['ir.module.module'].search_read(
    [('name', 'in', ['account', 'account_asset'])],
    ['name', 'state', 'latest_version']
)

for model_name in (
    'account.asset',
    'account.asset.asset',
    'account.asset.category',
    'account.asset.depreciation.line',
):
    print(model_name, model_name in env.registry.models)

if 'account.asset' in env.registry.models:
    print(env['account.asset']._fields.keys())
```

Do not infer model names from older Odoo versions. Odoo 17 deployments
differ by edition, installed addons and third-party modules.

### Backend selection

**Option A --- Native backend available and approved** - Implement a
bridge/adapter around the deployed native asset model. - Map BUZ asset
to native asset with a unique relation. - Delegate schedule calculation
and accounting moves to native implementation. - Extend native records
through supported model inheritance. - Verify field names and method
signatures from installed source before coding.

**Option B --- No compatible native backend** - Implement custom
schedule model and accounting backend using `account.move`. - Own
calculation, move creation, posting, reversal and reconciliation. - Do
not create a fake native model with a conflicting name. - Keep adapter
contract identical to Option A.

**Hard rule:** only one engine owns an asset's depreciation schedule and
postings.

## 3. Addon dependency strategy

Core manifest dependencies:

``` python
{
    "name": "BUZ Asset Management",
    "version": "17.0.1.0.0",
    "depends": ["base", "mail", "web", "account", "hr"],
    "data": [
        # security, sequences, views, reports, cron
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
```

Do not declare `account_asset` as a hard dependency until deployment
discovery confirms the exact technical module and edition availability.
If a native backend is required, create a separate bridge addon such as
`buz_asset_account_asset_bridge` depending on both the core module and
verified native technical module.

Add optional dependencies such as `stock`, `maintenance`, `fleet` or
barcode addons only when their workflows are genuinely integrated.

## 4. High-level component diagram

``` mermaid
flowchart TD
    UI[Odoo Web UI / Mobile] --> CORE[BUZ Asset Management]
    CORE --> REG[Asset Register & Lifecycle]
    CORE --> OPS[Transfer / Audit / Maintenance / Warranty]
    CORE --> REP[Reports & Dashboard]
    REG --> ACQ[Acquisition Service]
    ACQ --> BILL[account.move Vendor Bill]
    REG --> ADAPTER[Accounting Backend Adapter]
    ADAPTER --> NATIVE[Native account_asset Backend]
    ADAPTER --> CUSTOM[Custom Depreciation Backend]
    NATIVE --> MOVE[account.move / account.move.line]
    CUSTOM --> MOVE
    MOVE --> GL[General Ledger]
    REP --> MOVE
    REP --> REG
```

Native and custom are alternative backends. Never run both for the same
asset.

## 5. Data model design

Use `buz.asset.*` namespace. Include explicit `company_id`,
`currency_id`, `active`, audit metadata and `mail.thread` /
`mail.activity.mixin` where useful.

### 5.1 `buz.asset`

Core fields: - `name`, `code` (unique per company; immutable after
approval). - `company_id`, `currency_id`, `category_id`. -
`source_type`: `vendor_bill`, `manual`, `opening_balance`, `donation`,
`self_constructed`, `other`. - `source_ref`, `vendor_id`, `bill_id`
(`account.move`), `bill_line_id` (`account.move.line`). -
`allocated_bill_amount`. - `purchase_date`, `in_service_date`,
`depreciation_start_date`. - `gross_cost`, `residual_value`,
computed/validated `depreciable_base`. - `useful_life_months`,
`depreciation_method`, `depreciation_frequency`. - `accounting_backend`,
immutable after depreciation posting. - Optional `native_asset_id` only
when exact native model exists. - `department_id`, `employee_id`,
`location_id`. - `parent_asset_id`, `child_asset_ids`. -
`serial_number`, `manufacturer`, `model`, `barcode`, `qr_token`. -
Warranty/insurance fields. - Separate `operational_state`,
`approval_state`, `accounting_state`. - `disposal_id`, `disposal_date`,
notes and attachments.

Constraints: - Unique `(company_id, code)`. - `gross_cost >= 0`,
`residual_value >= 0`, `residual_value <= gross_cost`. - Useful life \>
0 for depreciable assets. - Bill source requires valid vendor bill and
bill line from same company. - Bill allocation cannot exceed eligible
bill-line amount. - Prevent duplicate allocation. - No cross-company
employee, department, location, journal, account or move links. -
Prevent parent cycles.

For bill-derived assets, allocation record is authoritative for the
portion capitalized; do not copy the full bill line amount to every
asset.

### 5.2 `buz.asset.category`

Fields: - Name, code, global/company scope. - Sequence/prefix, tracking
mode (individual/grouped). - Default useful life, method, frequency,
start policy and prorata rule. - Fixed asset, accumulated depreciation,
expense, gain/loss and disposal clearing accounts. - Journal and
analytic distribution. - Approval configuration, maintenance defaults
and QR requirement.

Validate account company and account type. Do not hardcode chart of
accounts.

### 5.3 `buz.asset.acquisition` and `.line`

Acquisition header: - `bill_id`, `bill_line_id`, `company_id`,
`currency_id`. - `line_eligible_amount`, `allocated_amount`,
`remaining_amount`. - Allocation lines, state and approval details.

Allocation line: - Acquisition, asset, quantity/count and allocated
amount. - Unique relationship preventing duplicate source allocation. -
Validate sum against eligible bill-line amount with currency rounding.

### 5.4 `buz.asset.depreciation.line`

Use only for custom backend. If native backend is selected, map/display
native schedule lines rather than creating a second schedule.

Fields: - `asset_id`, `company_id`, `sequence`, `name`. -
`depreciation_date`, `period_start`, `period_end`. - `planned_amount`,
`posted_amount`, `remaining_after`. - State: `planned`, `draft_move`,
`posted`, `reversed`, `cancelled`, `exception`. - `move_id`
(`account.move`). - Unique `idempotency_key`, `calculation_version`,
`calculation_snapshot`, `exception_message`.

Schedule is a plan. Posted balances derive from posted move lines, not
manually maintained counters.

### 5.5 `buz.asset.transfer`

Sequence, company, asset, effective date, from/to employee, department
and location, requestor, approver, completer, state, reason,
acknowledgement, attachments and immutable previous-custody snapshot.

### 5.6 `buz.asset.location`

Name, code, company, parent location, address, active and optional type
(site/building/floor/room/storage/other). Enforce company consistency
and prevent recursive hierarchy.

### 5.7 `buz.asset.maintenance`

Sequence, asset, company, type, planned/actual dates, vendor,
technician, description, result, cost, currency, downtime, warranty
coverage, attachments and state. Maintenance cost is operational data,
not automatic capitalization.

### 5.8 `buz.asset.audit` and `.line`

Campaign: sequence, company, date, scope filters, responsible user,
state, snapshot timestamp and completion metrics.

Line: campaign, asset, immutable expected location/custodian snapshot,
actual location/custodian, scan timestamp/user, condition, result,
photo, notes and resolution. Unique `(campaign_id, asset_id)`.

### 5.9 `buz.asset.disposal`

Sequence, asset, company, disposal date/method/reason, proceeds, costs,
buyer/customer, invoice reference, carrying-value snapshot, accumulated
depreciation snapshot, gain/loss, journal move and state.
Compute/validate from posted accounting data as of disposal date.

## 6. Accounting backend contract

Define an abstract service contract (Python service class or abstract
model):

``` python
class AssetAccountingBackend:
    def prepare_asset(self, asset):
        # Create or link accounting asset representation.

    def get_depreciation_schedule(self, asset):
        # Return normalized schedule rows.

    def preview_depreciation(self, asset, date_to=None):
        # Return non-posting preview.

    def post_depreciation(self, asset, schedule_line, accounting_date=None):
        # Create/post accounting move safely.

    def reverse_depreciation(self, asset, schedule_line, reversal_date, reason):
        # Reverse using supported Odoo APIs.

    def get_book_value(self, asset, as_of_date=None):
        # Return posted cost, accumulated depreciation and NBV.

    def dispose_asset(self, disposal):
        # Prepare/post disposal accounting entries.

    def reconcile(self, company, date_from, date_to):
        # Return subledger vs GL comparison and exceptions.
```

Normalize native/custom differences into the same result structure. Do
not expose native model field names across the BUZ module.

## 7. Accounting integration

### Vendor Bill

-   Extend `account.move` with smart button/context action.
-   Validate `move_type == 'in_invoice'`; refunds are excluded unless
    explicitly enabled.
-   Require posted bill for MVP.
-   Exclude display, tax, payable and ineligible lines.
-   Validate eligible account/category and company.
-   Do not modify the posted bill.
-   If native automation created an asset, link BUZ details to it
    through bridge.

### Journal entry generation

Use ORM: - Create `account.move` with `move_type='entry'`. - Set
company, journal, date, ref and line commands. - Create balanced
`account.move.line` entries with account, debit, credit, label and
optional analytic distribution. - Validate using company currency
rounding. - Call `action_post()` only after validations. - Link move to
schedule/disposal record. - Never write accounting rows using SQL.

Allow Odoo and installed accounting extensions to validate lock dates
and policies. Catch user-correctable errors and show actionable
messages; do not swallow exceptions.

### Lock dates and custom Accounting Date Policy

-   Read and respect actual Odoo 17 lock-date fields and installed
    custom policies.
-   Never bypass validation through context flags, SQL or elevated
    writes.
-   If planned date is blocked, leave line pending/exception and offer a
    permitted-date workflow.
-   Any override must be a separate audited Accounting Manager process
    and still comply with Odoo validation.

### Idempotency and concurrency

-   Unique key such as `asset_id:schedule_line_id:depreciation`.
-   Check existing linked move and state before posting.
-   Use database uniqueness and transaction boundaries; UI button
    disabling is insufficient.
-   Cron processes bounded batches, logs per-line failures and is safe
    to rerun.
-   Use row locking only when necessary and compatible with ORM
    transaction semantics.

### Multi-currency

-   Distinguish source currency amount from company-currency
    capitalization.
-   Use Odoo currency conversion at approved accounting date.
-   Store currency and conversion basis/date where needed.
-   Depreciation moves use company currency unless configuration
    dictates otherwise.
-   Reconcile using Odoo currency rounding.

## 8. Service layer

Recommended services: - `AssetRegistrationService` -
`AssetAcquisitionService` - `AssetDepreciationService` -
`AssetTransferService` - `AssetAuditService` - `AssetDisposalService` -
`AssetReconciliationService` - `AssetNotificationService`

Keep business validation in model/service methods, not XML or
JavaScript.

## 9. Security architecture

Groups: - `group_asset_user` - `group_asset_officer` -
`group_asset_manager` - `group_asset_accountant` -
`group_asset_accounting_manager`

Baseline: - User: read assets/categories/locations; create audit
observations. - Officer: create/write draft assets, transfers,
maintenance and audit records. - Manager: approve operational
transitions and disposal requests. - Accountant: read assets and manage
depreciation preview/schedule subject to accounting groups. - Accounting
Manager: approve/post/reverse accounting actions.

Record rules: - Company isolation using allowed `company_ids`. -
Department scope only if explicitly required; Finance may need
cross-department visibility. - Audit/transfer records inherit company
isolation from linked asset. - No public asset read through QR. -
Attachments inherit parent record access.

Posting/reversal/disposal methods must check group and company access in
Python.

## 10. UI architecture

Use standard Odoo views: - Window actions for list/form/kanban. - Search
views with filters and group-by. - Pivot/graph for analytics. - Smart
buttons to bill, journal entries, transfers, maintenance and audit. -
Wizards for bill allocation, transfer, audit campaign, depreciation
preview and disposal. - QWeb PDF for labels/register.

Odoo 17 rules: - Use expression modifiers such as
`invisible="state != 'draft'"`. - Do not use legacy `attrs` or
`states`. - Prefer standard widgets; custom JS only when necessary. -
Buttons call server methods with full validation.

Responsive UX: - Prioritize mobile scan/audit. - Avoid redundant
sidebars and dense dashboard cards. - Use Odoo responsive layouts, not a
separate SPA.

## 11. Scheduled jobs and notifications

Jobs: - Warranty expiry reminders. - Depreciation due
notifications/processing. - Maintenance due reminders. - Audit campaign
reminders.

Default depreciation policy: **prepare/notify, not auto-post**, until
Accounting explicitly enables auto-post. Auto-post must process only
approved lines on open dates with strict idempotency.

Cron must be batch-limited, company-aware, log exceptions, avoid
duplicate messages, be safe to rerun and never silently skip failures.

## 12. Reporting

Use ORM read/grouping or read-only optimized SQL only when justified.
SQL must never write business records.

Reconciliation: - Fixed asset cost GL vs asset gross cost, adjusted for
disposals/opening balances. - Accumulated depreciation GL vs posted
depreciation by asset. - Net book value. - Unmatched GL lines and
unmapped assets. - Company/date/account/currency filters and drill-down
to move lines and assets.

Clearly distinguish operational asset count from accounting balance.

## 13. Testing

1.  Unit tests for depreciation math/date rules.
2.  Model tests for constraints, sequence, source allocation and
    transitions.
3.  Accounting tests for balanced moves, accounts, company and lock
    dates.
4.  Idempotency tests for duplicate button/cron execution.
5.  Access tests for groups and multi-company rules.
6.  Workflow tests for transfer, audit, maintenance and disposal.
7.  Install/upgrade tests on clean Odoo 17 database.
8.  Performance tests for large register and audit campaigns.

Use a real Odoo 17 test database with relevant addons and custom
accounting policy. Mock external integrations only, not accounting
posting.

## 14. Suggested addon structure

``` text
buz_asset_management/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── asset.py
│   ├── asset_category.py
│   ├── asset_location.py
│   ├── asset_acquisition.py
│   ├── asset_transfer.py
│   ├── asset_maintenance.py
│   ├── asset_audit.py
│   ├── asset_disposal.py
│   ├── account_move.py
│   └── res_company.py
├── services/
│   ├── __init__.py
│   ├── registration.py
│   ├── acquisition.py
│   ├── accounting_backend.py
│   ├── depreciation.py
│   ├── transfer.py
│   ├── audit.py
│   ├── disposal.py
│   └── reconciliation.py
├── wizard/
│   ├── __init__.py
│   ├── asset_bill_allocation.py
│   ├── asset_transfer.py
│   ├── asset_audit.py
│   ├── asset_depreciation.py
│   └── asset_disposal.py
├── security/
│   ├── asset_security.xml
│   └── ir.model.access.csv
├── data/
│   ├── asset_sequence.xml
│   ├── asset_cron.xml
│   └── mail_template.xml
├── views/
│   ├── asset_views.xml
│   ├── category_views.xml
│   ├── location_views.xml
│   ├── acquisition_views.xml
│   ├── transfer_views.xml
│   ├── maintenance_views.xml
│   ├── audit_views.xml
│   ├── disposal_views.xml
│   ├── account_move_views.xml
│   ├── dashboard_views.xml
│   └── menu_views.xml
├── report/
│   ├── asset_label_report.xml
│   ├── asset_register_report.xml
│   └── report_templates.xml
├── static/description/
├── tests/
│   ├── __init__.py
│   ├── common.py
│   ├── test_asset_registration.py
│   ├── test_depreciation.py
│   ├── test_accounting.py
│   ├── test_transfer_audit.py
│   ├── test_disposal.py
│   └── test_security.py
└── README.md
```

If using native backend, add a separate bridge addon
`buz_asset_account_asset_bridge/` depending on the core module and
verified native technical module.

## 15. Implementation sequence

1.  Inspect deployment and decide backend.
2.  Create skeleton, manifest, groups, ACLs and company rules.
3.  Implement category, location and asset register.
4.  Implement bill allocation and manual/opening registration.
5.  Implement accounting adapter and depreciation schedule.
6.  Implement posting, lock-date handling, reversal and reconciliation.
7.  Implement disposal.
8.  Implement transfer, maintenance, warranty and audit.
9.  Implement QR, reports and dashboard.
10. Run Odoo tests, UAT and migration rehearsal.

Do not code the depreciation engine before backend discovery is
complete.
