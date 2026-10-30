# CLAUDE.md --- Instructions for Claude Code

## Project

Build `buz_asset_management`, a production-quality custom addon for
**Odoo 17.0**.

It is a full fixed-asset lifecycle module integrated with Odoo
Accounting. It supports Vendor Bill and manual registration, accounting
depreciation only, transfers, QR labels, physical audits, maintenance,
warranty, disposal and reconciliation.

Read these first: - `PRD.md` --- product requirements and acceptance
criteria. - `ARCHITECTURE.md` --- data model, integration boundaries,
security and implementation strategy.

Treat these as project specifications. If a financial policy is
ambiguous, ask before implementing it.

## 1. Non-negotiable rules

1.  Target Odoo 17.0. Verify APIs against the actual 17.0 source; do not
    assume APIs from 16/18/19.
2.  Inspect repository, addons path, installed modules and
    customizations before editing.
3.  Determine whether a compatible native `account_asset` backend
    exists. Verify actual models, fields and methods. Do not guess.
4.  Exactly one depreciation engine per asset: native backend OR custom
    backend.
5.  `account.move` / `account.move.line` are accounting source of truth.
6.  Never create or update accounting records using direct SQL.
7.  Never bypass Odoo lock dates, Accounting Date Policy, journal
    restrictions or posting validation. No undocumented context flags or
    `sudo()` to force posting.
8.  Never delete or silently modify posted moves. Corrections use
    reversal/adjustment.
9.  Accounting actions must be balanced, company-consistent,
    currency-aware and auditable.
10. Accounting actions and cron jobs must be idempotent.
11. Enforce permissions server-side; UI visibility is not security.
12. Support multi-company with strict company consistency and record
    rules.
13. Use Odoo 17 expression modifiers. Do not use legacy `attrs` or
    `states` XML attributes.
14. Do not invent account codes, depreciation policies, capitalization
    thresholds or date conventions. Make configurable and ask when
    ambiguous.
15. Do not modify core Odoo files or add unrelated dependencies.

## 2. First actions before implementation

Start by: - Listing project files and Git status. - Identifying Odoo
source version and addons paths. - Checking whether `account_asset` is
installed and inspectable. - Inspecting custom modules that alter
`account.move`, accounting dates, lock dates or asset creation. -
Reviewing exact deployed asset model and APIs. - Checking relevant HR,
web, barcode, maintenance and stock modules. - Running existing tests
before changes if environment is available.

Create `IMPLEMENTATION_NOTES.md` recording: - Environment/version
findings. - Native-vs-custom backend decision and evidence. - Existing
customizations affecting posting. - Assumptions needing owner
approval. - Planned implementation steps.

Do not start depreciation implementation until backend decision is
documented.

Example Odoo shell discovery (adapt to actual environment):

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
```

If native `account_asset` is available, inspect installed fields,
compute/post methods, views and tests. If unavailable or unsuitable,
implement custom backend behind the architecture contract.

## 3. Development workflow

Work in small, reviewable increments: 1. Add/update one coherent
feature. 2. Add tests in the same change. 3. Run syntax/lint and
relevant Odoo tests. 4. Inspect diff for accidental changes and unsafe
accounting behavior. 5. Update docs and implementation notes. 6. Report
completed work, tests, failures and open decisions.

Never claim tests passed unless actually executed. If Odoo is
unavailable, state tests were not run and provide exact commands.

Read existing files before changing them. Preserve local conventions
unless they conflict with this specification.

## 4. Coding standards

### Python

-   Use Odoo ORM, `models.Model`, `models.TransientModel`, `fields`,
    `api`.
-   Use Odoo 17-compatible constraint mechanisms; verify decorators/APIs
    against installed source.
-   Use `@api.model_create_multi` for multi-create where appropriate.
-   Use `fields.Monetary` with explicit currency field.
-   Use Odoo date utilities and `fields.Date.context_today()`.
-   Use `float_compare` / `float_is_zero` with currency rounding; never
    compare monetary floats with raw `==`.
-   Avoid raw SQL. Read-only optimized SQL is allowed only with
    justification and parameterized queries; never use SQL for business
    writes.
-   Avoid broad `sudo()`. If elevation is essential, scope narrowly,
    document why and retain company/authorization checks.
-   Raise clear `UserError` / `ValidationError`.
-   Translate user-facing strings with `_()`.
-   Avoid N+1 queries; batch operations and use ORM prefetch patterns.

### XML

-   Use Odoo 17 XML syntax.
-   Use expression modifiers such as `invisible="state != 'draft'"`.
-   Never use `attrs` or `states`.
-   Restrict accounting buttons by groups and validate again in Python.
-   Avoid duplicate menus and unnecessary navigation.

### Views / UX

-   Modern, compact, responsive.
-   Standard Odoo list/form/kanban/search/pivot/graph where appropriate.
-   Real dashboard figures, not hard-coded demo values.
-   Mobile audit flow: scan, identify asset, show custodian/location,
    record result.
-   Separate planned values from posted accounting values.
-   No custom JS unless standard widgets cannot satisfy requirement.

### Naming

-   Models: `buz.asset`, `buz.asset.category`, etc.
-   XML IDs: `buz_asset_management.<descriptive_id>`.
-   Python files: snake_case.
-   Sequences: `buz.asset.*`.
-   Explicit methods: `action_submit`, `action_approve`,
    `action_post_depreciation`.

## 5. Accounting implementation requirements

### Source registration

-   Vendor Bill source references actual `account.move` and
    `account.move.line`.
-   Default to posted Vendor Bills.
-   Exclude tax, payable, display and ineligible lines.
-   Support split allocations.
-   Validate total allocation against eligible line amount using
    currency rounding.
-   Prevent duplicate capitalization.
-   Manual assets require source reason and evidence.
-   Manual registration must not silently post accounting entries.

### Depreciation

-   Accounting depreciation only; no tax schedule in MVP.
-   Straight-line MVP formula:
    `max(0, gross_cost - residual_value) / number_of_periods`.
-   Round by company currency; final period absorbs remainder.
-   Implement start-date/prorata rules only after owner approval.
-   Distinguish planned and posted amounts.
-   Journal entry: debit depreciation expense, credit accumulated
    depreciation.
-   Use configured accounts/journal and optional analytic distribution.
-   Validate company, currency, date, accounts and journal.
-   Respect lock dates and custom Accounting Date Policy.
-   If posting is blocked, leave pending/exception and show actionable
    message. Never force-post.
-   Idempotency key prevents duplicate moves under repeated or
    concurrent cron/action.
-   Use selected backend adapter; do not duplicate native schedule
    logic.

### Reversal and disposal

-   Reverse through supported Odoo API.
-   Keep original move and link reversal.
-   Disposal carrying value uses posted accounting data at disposal
    date.
-   Sale invoice must not duplicate proceeds/revenue.
-   Post disposal only after approval/date validation.
-   Stop future depreciation after disposal.
-   Preserve source links and audit history.

**Critical:** customer environment may contain a custom Accounting Date
Policy. Inspect and honor it. Never bypass a fail-closed policy, lock
date or journal control.

## 6. Security requirements

Implement groups: - `group_asset_user` - `group_asset_officer` -
`group_asset_manager` - `group_asset_accountant` -
`group_asset_accounting_manager`

Implement ACLs and multi-company rules. Test: - User cannot read
unauthorized company's assets. - Asset User cannot approve, post or
dispose. - Asset Officer cannot post depreciation unless separately
authorized. - Only authorized Accounting Manager/Odoo accounting group
can post or reverse. - RPC calls cannot bypass state transition
checks. - QR token does not grant public access.

A button's `groups` attribute is not enough.

## 7. Required test coverage

### Registration

-   Manual creation.
-   Vendor Bill creation.
-   Split allocation.
-   Allocation overrun rejected.
-   Duplicate source allocation rejected.
-   Invalid company/account/vendor links rejected.
-   Unique sequence per company.

### Depreciation

-   Straight-line total equals depreciable base within currency
    rounding.
-   Final period absorbs remainder.
-   Zero/negative base handled.
-   Start-date/prorata edge cases.
-   Leap year and month-end.
-   Multi-currency conversion.
-   Balanced move and correct debit/credit accounts.
-   Wrong company/journal/account rejected.
-   Repeated action does not duplicate move.
-   Repeated/concurrent cron is idempotent.
-   Locked date/custom policy blocks posting.
-   Reversal preserves original and links reversal.

### Operations

-   Transfer approval and history snapshot.
-   Company mismatch rejected.
-   Audit snapshot remains unchanged after asset location changes.
-   QR requires authorization.
-   Maintenance does not automatically capitalize.
-   Warranty reminder is not duplicated.

### Disposal/reporting

-   Carrying value uses posted entries.
-   Sale proceeds not double-counted.
-   Gain/loss is balanced.
-   No depreciation after disposal.
-   Reconciliation exposes variances and drill-down.
-   Multi-company access rules.

## 8. Commands and validation

Adapt paths/database names. Never run destructive commands on
production.

``` bash
./odoo-bin \
  --addons-path=addons,custom_addons \
  -d buz_asset_test \
  -i buz_asset_management \
  --test-enable \
  --stop-after-init \
  --log-level=test
```

For upgrades, use a disposable test database and
`-u buz_asset_management`.

Also run Python compilation/lint configured by repository, XML
validation through Odoo installation, dependent bridge tests and manual
UAT on a production copy.

Do not run `-i` or `-u` against production without approved backup and
deployment window.

## 9. Definition of done

A feature is complete only when: - Business requirement implemented. -
ACLs and record rules in place. - Unit/model/integration tests added. -
Odoo 17 install/upgrade tested. - No accounting bypass or duplicate
posting risk remains. - UI usable on desktop and mobile where
relevant. - Documentation updated. - Limitations and untested areas
reported.

For release: - PRD acceptance criteria checked or explicitly deferred. -
Backend decision documented. - Depreciation policy signed off by
Finance. - Reconciliation test passes on controlled dataset. - Backup,
rollback and deployment steps documented.

## 10. Progress report format

At each milestone report: 1. Files created/modified. 2. Features
completed. 3. Tests executed and exact results. 4. Accounting/security
risks found. 5. Decisions needed from owner. 6. Next smallest
implementation step.

Do not fabricate successful installation, test results, journal postings
or production readiness.
