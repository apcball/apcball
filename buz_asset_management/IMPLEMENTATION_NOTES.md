# IMPLEMENTATION_NOTES.md — buz_asset_management

Status: **discovery done (DEV + PROD read-only). Backend decision: Option B (custom) recommended, owner sign-off pending.**
Last updated: 2026-10-30

## 1. Environment findings

| Item | DEV (MOG_DEV) | PROD (MOG_LIVE) |
|---|---|---|
| Odoo | 17.0 docker | 17.0 systemd (instance1) |
| Enterprise `account_asset` | not in repo, not in `ir_module_module` | not present (`account.asset` not in registry) |
| `om_account_asset` 17.0.1.0.3 (OdooMates, community) | installed | installed |
| `om_account_accountant`, `om_fiscal_year` | installed | installed |
| `base_accounting_kit` | uninstalled | uninstalled |
| `buz_accounting_date_control` 17.0.1.0.0 | installed | **not installed** (no module row, no policy model) |
| `hr` | installed | installed |
| `maintenance`, `fleet` | uninstalled | uninstalled |
| `barcodes` | installed (`stock_barcode` uninstallable) | installed |
| Companies | 1 (บริษัท โมเก้น จำกัด, THB) | 1 (same, THB) |
| Fiscal/period/tax lock dates | all NULL | all unset |
| `om` assets / categories / depreciation lines | 0 / 0 / 0 | 0 / 0 / 0 (0 posted lines, 0 bill-linked, 0 bill lines with `asset_category_id`) |
| Date policy row | company 1: max_back_days=365, max_future_days=30, active | none (module absent) |
| `om` cron "Generate asset entries" | not checked | active, next 2026-11-09 (harmless while 0 assets) |

Repo has no Enterprise `account_asset`. Only `om_account_asset` (+ copies inside `base_accounting_kit`).

## 2. om_account_asset findings (source read: `om_account_asset/models/`)

- Models: `account.asset.asset`, `account.asset.category`, `account.asset.depreciation.line`. These are the legacy names the architecture doc warns about, not Odoo 17 Enterprise `account.asset`.
- `account.move.action_post` override calls `asset_create()` per invoice line that has `asset_category_id`. **Native auto-creation from vendor bills exists.** BUZ bill allocation must link or extend, never duplicate (PRD 3.2.A).
- Monthly cron `_cron_generate_entries` calls `compute_generated_entries(today)` and posts depreciation entries automatically. It has **no idempotency key** beyond `line.move_id` check, and it **auto-posts**. PRD wants prepare/notify by default.
- `create_move` posts only when category `open_asset` is set. Grouped-entry path (`create_grouped_move`) uses `fields.Date.today()` for conversion and ignores per-line dates.
- `button_draft` / `action_cancel` write `active=False` on linked assets via `sudo()`.
- Depreciation entries go through normal `account.move.create`, so `buz_accounting_date_control` validates them. No bypass context used by om.
- Schedule supports linear and degressive, prorata flag, `method_time` number/end. Prorata convention is om's, not an approved BUZ policy.

## 3. Customizations affecting posting

- `buz_accounting_date_control` (override of `account.move.create` / `write`): fail-closed if no company policy; blocks dates beyond max back/future days. It exposes context flag `buz_override_date_control` for date admins. **BUZ must never set it.**
- ~50 addons `_inherit` `account.move` (list: `grep -rl "_inherit = 'account.move'"`). Most relevant: `buz_accounting_date_control`, `om_account_asset`, `om_account_accountant`, `od_journal_sequence`, `buz_mrp_backdate`, `l10n_th_account_tax`, `buz_th_vat_undue`, `employee_advance`. None reviewed in depth yet.
- Lock-date code present in `om_fiscal_year`, `base_accounting_kit` (lock date wizard), `buz_valuation_regenerate`, `fifo_reset_engine`. Standard Odoo lock fields are NULL on DEV.

## 4. Backend decision

**Recommended: Option B (custom backend); owner sign-off pending.** Prod and DEV both have zero `om` asset data, so there is nothing to bridge or migrate. Evidence:

- Option A (native bridge): there is no Enterprise `account_asset`. Bridging `om_account_asset` is possible, but its engine auto-posts via cron and has no idempotency key, so BUZ would need to disable or wrap that cron.
- Option B (custom backend): matches the architecture contract and idempotency/lock-date rules, but needs co-existence with `om_account_asset` (its bill hook would still create assets from lines carrying `asset_category_id`).

Prod has no live `om` assets, so the bridge case does not apply today. Co-existence still needs handling: `om` bill hook and active cron must not touch BUZ assets (retire/uninstall `om_account_asset` or neutralize its `asset_category_id` hook; owner decision).

Rule to keep: exactly one engine per asset. Do not name any BUZ model `account.asset*`.

## 5. Assumptions needing owner approval

1. Is `om_account_asset` used on prod (asset count, posted depreciation entries)?
2. Is `om_account_asset` to be retired, kept for legacy assets only, or kept as the backend?
3. Depreciation convention (full month / prorata / half-month) — not approved, not implemented.
4. Capitalization threshold and eligible accounts.
5. Opening assets: journal entries or register-only.
6. Disposal gain/loss accounts, invoice linkage.
7. Inter-company transfers: assumed out of MVP.
8. Prod uses same date-policy values as DEV?

## 6. Not done / gaps

- Prod discovery done 2026-10-30 via read-only `odoo shell` (user-authorized, rolled back, no writes). Shell emitted a registry warning traceback in `res_users` read; output of the queries was complete.
- Odoo 17 core source not inspected (APIs unverified). Assume nothing from 16/18.
- No existing tests run. `om_account_asset` has no `tests/` dir in repo (not checked for `buz_accounting_date_control` beyond smoke file name).
- Other `account.move` overrides not reviewed.

## 7. Planned steps

1. Owner decision on section 5 items 2, 3 (retire `om_account_asset`? depreciation convention).
2. Backend decision recorded as final once approved.
3. Skeleton: manifest, groups, ACLs, company rules, sequences.
4. Category, location, asset register (+ tests).
5. Backend adapter + chosen engine. No depreciation code before step 2.

## 8. Owner decisions (2026-10-30)

- **Depreciation convention: full month.** A full period's depreciation is booked for the month the asset is in service, no day-count proration. Start-of-depreciation rules (which month counts as month 1 relative to in-service date) still need one confirmation before the schedule code is written.
- **`om_account_asset`: owner approved removal.** NOT yet executed.
  - Finding: `om_account_accountant` (installed on DEV and prod) depends on `om_account_asset`. Uninstalling `om_account_asset` cascades to uninstall `om_account_accountant`. No other repo manifest depends on `om_account_accountant`.
  - Nothing outside `om_account_asset` / `base_accounting_kit` references `account.asset.*` or `asset_category_id`.
  - Plan once approved: DEV first, review the cascade list, backup MOG_LIVE before prod.

## 9. Scaffold status (2026-10-30)

- Option 1 chosen for `om_account_asset`: keep installed, disable cron. DEV: `ir_cron` id 21 set `active=false` (was true, next 2026-11-09). **PROD: not yet changed** (cron id not recorded; prod access so far was read-only, write needs explicit OK).
- Created: manifest, groups (5), ACLs, global company rules, `buz.asset` sequence (prefix `AST/`, padding 5, noupdate), models `buz.asset.location`, `buz.asset.category`, `buz.asset`, views + menu, 12 tests.
- State fields (`approval_state`, `operational_state`, `accounting_state`) are blocked from direct create/write unless `env.su`; `action_*` methods check group + state, then write via `sudo()`. Chosen over context flags because RPC callers can pass context.
- Account-type validation on category accounts NOT implemented (type policy not approved). Company check only.
- Full-month convention recorded but no schedule code yet; month-1 rule (in-service month vs next month) still open.
- **Not run:** no Odoo install, no tests executed. Only `py_compile`, XML well-formedness, CSV shape and a grep for `attrs`/`states` were checked.

## 10. DEV install + test run (2026-10-30)

- Deployed to DEV by rsync (dirs need `a+rx`; `chmod -R +r` alone left dirs unreadable in the container) and installed with `-i` (`deploy.sh` only does `-u`, so it cannot do a first install). Module list refreshed with `update_list()` first.
- First install failed view validation: a field with `check_company` needs `company_id` in the form without a `groups` restriction. Fixed.
- Result: **10 passed, 2 skipped, 0 failed** (12 tests). Skipped: `test_cross_company_employee_rejected`, `test_cross_company_category_account_rejected`. MOG_DEV has orphaned NOT NULL columns on `res_company` (`po_lead`), so a second company cannot be created. Cross-company enforcement is therefore **not verified** yet.
- Test data needs `skip_partner_required_fields=True` on DEV (`buz_partner_required_fields` blocks creating partners without full address).
- DEV also has an unrelated installed addon `buz_it_asset` (not in repo root). Overlap with `buz.asset` not assessed.
- Prod: not deployed.

## 11. buz_it_asset review (2026-10-30)

- Addon `buz_it_asset` 17.0.1.16.0 (depends `buz_it_helpdesk`, `hr`, `mail`; not in repo root, DEV server only). ~3k lines. Models `buz.it.asset*`, `buz.it.software.*`, repair/maintenance linked to helpdesk tickets, IT dashboard.
- Scope: IT hardware/software registry only. Has asset tag per type/company/year sequences, assignment history, maintenance + parts, `purchase_price`, `warranty_end`. **No accounting link, no depreciation, no vendor-bill source, no disposal, no audit, no QR.**
- DEV data: 2 assets (both assigned), 2 assignments, 4 maintenance records, 2 locations.
- Overlap with `buz_asset_management`: custody, location, maintenance, warranty fields only. No model-name clash (`buz.it.*` vs `buz.asset.*`).
- Owner: `buz_it_asset` is not in use (2026-10-30). Prod state not checked.
- Decision: no integration; keep `buz.asset` independent. No migration of the 2 DEV records. Revisit only if IT wants IT hardware capitalized.

## 12. Prod cron + month-1 rule (2026-10-30)

- PROD: `ir_cron` id 21 "Account Asset: Generate asset entries" set `active=false` via ORM (was true, next 2026-11-09). Revert: `env['ir.cron'].browse(21).write({'active': True})`. `om_account_asset` stays installed; 0 assets.
- Month-1 rule (owner): **first period is the month the asset enters service** (in service 15 Mar -> period 1 = March, full month, no proration). Depreciation date = last day of that month. Last period absorbs rounding remainder.

## 13. Depreciation schedule (2026-10-30)

- Added `services/depreciation.py` (pure math, no ORM), model `buz.asset.depreciation.line`, `buz.asset.action_compute_schedule` (group `group_asset_accountant`), schedule tab + header button, Depreciation menu (read-only list).
- Convention (owner-approved): full month; period 1 = month of `depreciation_start_date or in_service_date`; accounting date = last day of month; last period absorbs remainder; each regular period capped at remaining base (never negative).
- Plan only: no journal entries, `move_id` stays empty, no posting/reversal/cron yet.
- Lines are read-only for every group (ACL read only). Rows are created/replaced via the action with scoped `sudo()`. Recompute allowed only while every line is `planned`; otherwise UserError (reversal/adjustment is a later step).
- `idempotency_key` = `asset_id:sequence:depreciation`, unique. `calculation_version` increments per recompute; `calculation_snapshot` stores inputs as JSON.
- Chatter post uses scoped `sudo()` with the acting user as author: accountants only have read on `buz.asset`, and without it `message_post` raised AccessError (found by test).
- DEV result: 29 tests, 2 skipped (cross-company, orphaned `po_lead` column), 0 errors. Includes 9 pure-math tests (even split, remainder, awkward amounts, zero/negative base, leap year, month-end start, year rollover) and 8 model/permission tests.
- Not verified: prod deploy; posting; schedule for tiny residual/rounding combos beyond the tested set; multi-currency (schedule uses asset currency = company currency by definition today).

## 14. Thai translation (2026-10-30)

- `i18n/th.po` generated from a DEV `--i18n-export` of the module (200 terms), msgstr filled by hand; placeholders (`%s`, `%(x)s`) checked identical to the source. English stays the source language; Thai shows only for users whose language is `th_TH`.
- Covers menus, actions, group names, field labels, selection values, view text (buttons, tabs, filters), constraint messages and Python `UserError`/`AccessError` messages.
- DEV check: 124/124 field labels, 36/41 selection values, 5/5 group names have `th_TH`; Python terms resolve (19 loaded).
- Not translated (5 selection values of the mail activity mixin: `activity_state` Overdue/Today/Planned, `activity_exception_decoration` Alert/Error): not exported for this module, not visible in the UI.
- Not checked visually in a browser.
- Regenerate after any new string: export pot on DEV, rerun the mapping, review new terms.

## 15. Location: warehouse + parent from system (2026-10-30)

- Owner request: Warehouse and Parent Location must be selectable from existing system data (DEV had 0 `buz.asset.location` rows, so the old self-referencing parent list was empty).
- `buz.asset.location.warehouse_id` -> `stock.warehouse`; `parent_id` now -> `stock.location` (internal usage, narrowed to the chosen warehouse). Warehouse change clears a mismatching parent; constraint rejects a parent from another warehouse. `no_create` on both fields (no stock data created from here).
- Removed `child_ids`, `parent_path`, recursion check (hierarchy now comes from `stock.location`). Manifest now depends on `stock`.
- DEV: 24 warehouses / 193 internal stock locations available. Upgrade ran on an empty table (no data migration). Tests: no errors; 3 new location tests (2 need warehouses; the cross-warehouse one skips if < 2). Thai terms added for Warehouse and the new constraint message.
- Prod: not deployed. `stock` is already installed there (warehouses in use), not re-verified for this change.

## 16. Thai as source language (2026-10-30)

- Owner request: whole module in Thai regardless of the user's language setting (all 90 DEV users are `en_US`, so `th.po` alone showed English).
- Python (field `string=`, selection labels, `_description`, constraint messages, `_()` messages), XML (menus, actions, groups, view labels) and manifest name/summary rewritten to Thai. Every field now has an explicit `string=`. Backup of the previous English version kept outside the repo (session scratchpad).
- Consequence: **English is no longer shipped.** `en_US.po` cannot override source strings in Odoo 17 (tested: file loads, DB value stays), so an English UI would need the source changed back.
- `i18n/th.po` now holds only the 38 standard chatter/activity/system field labels (Activities, Followers, Created by...). Those stay English for `en_US` users and Thai for `th_TH` users.
- Convention going forward: write new strings in Thai in code/XML.
- DEV: tests 0 errors (2 skipped: cross-company); DB shows Thai menu/field/view/module names for `en_US`.

## 17. Capitalize, posting, reversal, cron (2026-10-30)

- Added `buz.asset.action_capitalize` (accountant; register-only, no JE), `buz.asset.depreciation.line.action_post_depreciation` / `action_reverse` (accounting manager, checked in Python), `buz_asset_line_id` on `account.move` (blocks reset-to-draft and delete), `res.company.buz_asset_auto_post` (default off) and daily cron `_cron_post_due_lines` (bounded batch, per-line savepoint, only companies with auto-post on).
- Posting: Dr expense / Cr accumulated, journal + accounts from category, `FOR UPDATE NOWAIT` row lock + unique key + existing `move_id` check for idempotency. Lines must post in sequence order and not before their date. No sudo for the move, no `buz_override_date_control`.
- Blocked posting (policy/lock) -> savepoint rollback, line `exception` + message, retry allowed. Setup errors (missing account, wrong company, state) raise with no state change.
- **Finding 1:** Odoo 17 `account.move._post` silently shifts a date that violates a lock date to the next open period. Posting would succeed on the wrong date. Fixed: compare `move.date` to the schedule date inside the savepoint; a shift is treated as blocked.
- **Finding 2:** `buz_accounting_date_control` grants policy read only to date admin/auditor groups, so any other accountant posting an entry on DEV gets AccessError ("Access Denied ... buz.accounting.date.company.policy"). Pre-existing, outside this module; asset posting users need the auditor (read-only) group or that ACL widened. Not worked around with sudo. Needs owner decision before prod users post.
- Reversal uses `_reverse_moves(cancel=True)`; original kept, `reversal_move_id` linked, second call is a no-op.
- DEV tests: **53 run, 0 failed, 2 skipped** (cross-company, orphaned `po_lead`). 11 new posting tests (balanced move, repeat post, order, future date, permissions, missing account, lock-date exception + retry, reversal, move protected, cron flag + idempotency).
- Not done yet: vendor-bill allocation (step 5), disposal (step 6), concurrent-cron test (idempotency covered by key/lock only in single transaction), Thai strings for new fields not exported to `th.po`, not deployed to prod, not UI-checked in browser.

## 18. Disposal (2026-10-30)

- Model `buz.asset.disposal` (draft -> approved -> posted, cancel from draft/approved), sequence `DSP/`, views + menu, ACLs, company rule, `account.move.buz_disposal_id` (move protected like depreciation moves). Approve = asset manager, post = accounting manager (checked in Python); state/figure fields writable only through the workflow.
- Figures come from POSTED depreciation lines dated <= disposal date. Any such line not posted (planned/exception/reversed) blocks posting. Cost = `gross_cost`.
- Entry (one move): Cr asset cost; Dr accumulated depreciation; Dr clearing = proceeds; Dr/Cr gain-loss = proceeds - carrying value. Without a linked invoice no proceeds and no clearing line (loss = carrying value).
- Sale invoice: must be posted `out_invoice`, same company, and its revenue must sit on the category's disposal clearing account (else rejected). Proceeds = credit-debit on that account; disposal entry debits the same amount, so clearing nets to zero and proceeds are counted once.
- On post: later planned/exception lines -> `cancelled` (no depreciation after disposal), asset operational + accounting state -> `disposed`. Lock-date shift guard as in posting; failure leaves disposal `approved`, nothing written.
- One non-cancelled disposal per asset. Disposal date has no future/back rule of its own; Odoo lock dates + date policy apply.
- DEV tests: **59 run, 0 failed, 2 skipped** (cross-company). 6 new: scrap loss + stop depreciation, sale proceeds once, blocked until depreciation posted, permissions/state guard, repeat post + duplicate, lock date.
- Open: partial/credit-note proceeds, multi-currency invoice (balance read in company currency columns only, not tested with foreign currency), disposal of a grouped asset, Thai strings not in `th.po`, prod not deployed, UI not checked in browser.

## 19. Vendor bill allocation (2026-10-30)

- Added `buz.asset.acquisition` (asset <-> bill line, amount in company currency = line `balance`), wizard `buz.asset.register.wizard(.line)`, "สร้างทรัพย์สิน" button on posted vendor bills (officer group), `buz.asset.source_move_id`, `acquisition_ids`.
- Eligible line: posted `in_invoice`, `display_type='product'`, `balance > 0`. Tax, payable, section/note lines and refunds are excluded; a line carrying the legacy `om_account_asset` `asset_category_id` is excluded so the same cost is never capitalized twice.
- Wizard offers only the unallocated remainder per line; one row = one asset, extra rows split a line. Overrun checked in the wizard (after `FOR UPDATE` on the bill lines) and again by the model constraint; unique(asset, line) blocks duplicates.
- Creates draft assets only. No journal entry (cost is already in the GL via the bill). Bill reset-to-draft and cancel are blocked once any allocation exists. Deleting a draft asset frees its allocation (cascade).
- Allocation rows are created with a narrow `sudo()` inside the wizard after the officer-group check; direct write is refused.
- DEV tests: 11 new, run clean with the rest (0 errors in the log; runner reports 72 tests, 2 skipped cross-company).
- Open: non-recoverable VAT is not added to cost (only untaxed line balance is allocated); foreign-currency bills untested; changing an asset's `gross_cost` after allocation is not checked against its allocation; asset form has no allocation tab; Thai strings not in `th.po`; officers need Odoo invoice read access to use the button; prod not deployed; UI not checked in a browser.

## 20. Non-recoverable VAT in asset cost (2026-10-30)

- Owner decision: VAT that cannot be reclaimed is part of asset cost.
- DEV check: all active purchase taxes (7%, 0%, exempt, WHT) book VAT to 151000 with tax closing = recoverable. No non-recoverable tax exists yet; none is auto-detected.
- Rule: new boolean `account.tax.buz_vat_non_recoverable` (purchase, percent, > 0). Constraint: its invoice tax repartition line must have an account and must NOT be used in tax closing, so the VAT is really in the GL outside the VAT account and the subledger matches the GL. A tax booked to 151000 cannot be flagged (reclassification would need its own entry; not built).
- Eligible amount of a bill line = `balance` + VAT of flagged taxes on that line (`compute_all`, converted at the line's rate, rounded in company currency). Wizard default, over-allocation checks and constraint all use it.
- Owner action needed: create a purchase tax (e.g. "VAT 7% ขอคืนไม่ได้") with the tax repartition line on a non-closing account, flag it, use it on asset bills.
- Limits: only flagged taxes are computed (interaction with other taxes that affect base is not modeled); foreign currency untested; the GL account of the VAT line is not forced to equal the category asset account (reconciliation report, Phase 3, must handle).
- DEV tests: 76 run, 0 failed (4 new VAT tests). Note: DEV holds real UAT data created by the owner (asset AST/00461 with a posted depreciation entry); tests must not scan the whole DB.

## 21. Disposal UAT on DEV (2026-10-30)

- Method: Odoo shell on MOG_DEV as the owner's user, real category 22 (เครื่องจักร), real accounts and real date policy; script ended with `rollback()` (assets 1 / disposals 0 afterwards; AST/00461 untouched).
- A scrap (cost 120,000, 4 posted months = 10,000): entry Cr 122000 120,000 / Dr 123105 10,000 / Dr 428000 110,000, balanced, move posted on disposal date. Asset -> disposed/disposed, later lines cancelled, post-after-disposal blocked, move reset-to-draft blocked.
- B sale (cost 60,000, accum 10,000, invoice 50,000 on clearing 428000): carrying 55,000, proceeds 50,000, loss 5,000; entry Dr 123105 5,000 / Dr 428000 50,000 / Dr 428000 5,000 / Cr 122000 60,000. Proceeds counted once; net on 428000 across invoice + disposal = 5,000 debit (the loss).
- C unposted depreciation: posting blocked, message lists the missing periods.
- D date policy: disposal dated 852 days back refused by `buz_accounting_date_control` (max 365), nothing written.
- Not covered: browser UI, lock-date shift (unit test only), foreign currency, concurrent post.
- **Config findings (DEV categories 22 and 43):** expense account = accumulated depreciation account (123105 / 123106). A depreciation entry is Dr and Cr on the same account, so no P&L expense is booked. Clearing account = gain/loss account (428000). Both look like setup mistakes; fix before prod.
- AST/00461 has periods 2-4 (Jul-Sep) planned and overdue; its disposal stays blocked until they are posted.

## 22. Main menu, dashboard, reports (2026-10-30)

- Menu (sequence): Dashboard 5, Register 10, Categories 20, Depreciation 30 (accountant), [40/50/60 reserved: Transfer, Maintenance, Audit — no models yet, no empty menus], Disposal 70, Reports 80 (register, book value, depreciation, by department, by location, disposal), Configuration 90 (locations; categories menu moved to main, duplicate removed).
- `buz.asset` gained stored `accumulated_depreciation` (POSTED lines only, reversal lowers it) and `book_value` (cost - accumulated; disposed = 0). Pivot/graph/tree reports use these; no SQL view.
- Dashboard: TransientModel `buz.asset.dashboard` opened by a server action; KPIs are live reads under the user's access rights and selected companies (asset count, cost, accumulated, book value, pending approval, due-unposted depreciation, exception lines, open disposals) with drill-down buttons. No hard-coded demo numbers.
- DEV check (read-only shell): dashboard shows 1 asset, cost 50,000, accumulated 1,041.67, book value 48,958.33, 3 due-unposted lines; all six report actions load pivot/graph/tree views.
- Tests: 81 run, 0 failed (+5: book value on post/reverse, disposed = 0, dashboard vs drill-down, asset-user access, menu/action xmlids).
- Not built: Transfer, Maintenance, Audit/Physical Count menus (Phase 2); reports for movement, audit, GL reconciliation; audit-rate KPI. Not browser-checked; Thai only.

## 23. Phase 2 — Asset Transfer (2026-10-30)

- Model `buz.asset.transfer` (TRF/ sequence): draft -> submitted -> approved -> done; rejected / cancelled; reject/cancel can reopen to draft. Officer creates/submits/cancels/completes, manager approves/rejects, any asset user can acknowledge (recorded once, not a gate). Company rule + ACLs; group checked in Python; state and "from" fields refused on direct write.
- Scope: employee, department, location of one asset. Inter-company transfers refused (separate accounting flow, out of MVP).
- "From" values are a snapshot taken at create and never rewritten. Done transfers are read-only (no edit, no delete, no cancel). Completion refuses with a clear message if the asset's custody changed since the snapshot (stale request).
- One open (draft/submitted/approved) transfer per asset. Asset must be approved and not disposed. A request with no actual change cannot be submitted.
- Custody of an APPROVED asset can no longer be edited directly (employee/department/location): `buz.asset.write` raises and points to a transfer; draft assets stay freely editable; the transfer's completion writes through a narrow `sudo()`. Chatter on the asset records old -> new.
- UI: Transfer menu (seq 40), "โอนย้าย" button on approved assets, history tab on the asset form, "รายงานการโอนย้าย" (list + pivot) under Reports.
- DEV tests: 94 run, 0 failed (11 new: full flow + snapshot, partial change, no-change, direct-edit guard, permissions, overlap, stale snapshot, immutability, not-approved/disposed, reject/reopen/cancel, acknowledge).
- Open: attachments (use chatter attachments), no notification to the receiving employee, no approval of acknowledgement, bulk transfer wizard, grouped-asset quantity split, browser UI not checked, prod not deployed. Test employees need `skip_partner_required_fields` on DEV.

## 24. Phase 2 — Audit / physical count + QR (2026-10-30)

- Models: `buz.asset.audit` (AUD/, campaign) and `buz.asset.audit.line`; scan wizard `buz.asset.audit.scan.wizard`. Campaign states draft -> in_progress -> closed / cancelled. Scope = company + optional departments / locations / categories (approved, non-disposed assets). `action_start` (officer) freezes the scope and snapshots expected employee/department/location per asset; lines are unique per (campaign, asset).
- Results: not checked, found, not found, wrong location, wrong custodian, damaged, retired. Any asset user records a count through buttons (`_record`, narrow `sudo()`); result, scanner, timestamp and the expected snapshot are write-guarded. Wrong location / custodian require an actual value different from the expected one. Observations never write to the asset; "found" copies the expected values into actual.
- Exceptions: officer sets a resolution (transfer / corrected / investigating / disposal / accepted) and can open a pre-filled transfer from the line. Close (manager) requires every line checked and every exception resolved; a closed or cancelled campaign is read-only.
- Metrics on the campaign (total, checked, exceptions, unresolved, completion %) and the dashboard (open campaigns, audit rate); report "ผลการตรวจนับ" (pivot by campaign x result).
- QR: label content = `<base_url>/buz_asset/qr/<qr_token>` (opaque uuid, no accounting data). Route `auth='user'` + record rules via `buz.asset._qr_target_url`: unknown token and unreadable asset both -> 404. A pending audit line for that asset takes priority, so a phone camera scan lands on the count form after login. PDF label report (QWeb, standard `/report/barcode` QR, officer group) bound to the asset list/form.
- Scanning: no custom JS. Phone camera app -> QR link; keyboard-wedge/bluetooth scanners or typing into the scan wizard (matches asset code, barcode, serial number, QR token or full URL). No in-browser camera widget.
- DEV tests: 110 run, 0 failed (14 new: snapshot scope + immutability, results leave asset untouched, found copy, wrong-* validation, permissions, frozen scope, close rules, completion rate, transfer from line, scan wizard by code/serial/URL/token, QR payload + authorization, QR -> audit line, label render).
- NOT verified: the HTTP route itself (tests run `--no-http`; unauthenticated DEV requests return 404 for every `auth=user` route because no DB is selected, so that says nothing about this route); in-browser/mobile UI; real label printing; multi-company access (DEV cannot create a second company); photo upload on a phone.
- Open: camera scanning inside Odoo, offline counting, recount/second-pass, assignment of lines to individual counters, audit approval workflow beyond manager close, maintenance and warranty (still Phase 2).

## 25. Phase 2 — Maintenance (2026-10-30)

- Models `buz.asset.maintenance` (MNT/) and `buz.asset.maintenance.part`. Types: preventive, corrective, inspection, calibration, other. States draft -> planned -> in_progress -> done, cancelled (reopen to draft). Fields: planned date, actual start/end (set by the workflow), responsible user, vendor (partner), technician (free text), warranty-covered flag, downtime hours, labour cost + parts (qty x unit cost) -> total cost, result, optional recurrence (months). Attachments via chatter.
- Permissions: asset user reads; officer does everything (plan/start/done/cancel). State and actual-time fields refused on direct write; done/cancelled jobs and their parts are locked (edits and delete refused).
- Cost is operational only: nothing writes to the asset's cost/book value or to any journal entry (tested: asset cost, book value and account.move count unchanged after a costed job).
- Asset state: while any job is in progress the asset is `under_maintenance`; restored to `in_service` when none remain (done or cancelled). Depreciation posting now accepts `in_service` and `under_maintenance` (otherwise a repair would have silently stopped monthly depreciation); covered by a test.
- Reminders: daily cron `_cron_remind_due` creates ONE activity per planned job within 7 days of its planned date (`reminder_sent` flag, rerun-safe, batch-limited). A job with recurrence creates ONE activity for the next round when done, not a new record. Overdue = planned and planned date before today (searchable filter, row highlight, dashboard tile with drill-down).
- UI: Maintenance menu (50), "แจ้งงานบำรุงรักษา" button and history tab on the asset, report "ค่าบำรุงรักษา" (pivot by month x type: cost and downtime), dashboard tiles open / overdue.
- DEV tests: 125 run, 0 failed (12 new + 1 depreciation-while-under-maintenance).
- Open: warranty tracking proper (provider, end date, expiry reminders, insurance — next Phase 2 item); the `warranty_covered` flag is manual and not linked to a warranty end date; vendor-bill link for repair costs; approval for expensive jobs; browser UI unchecked; prod not deployed.

## 26. Phase 2 — Warranty and insurance (2026-10-30)

- Model `buz.asset.coverage`: type warranty / insurance, provider (partner), reference or policy number, start/end, coverage, terms, insured amount (insurance), responsible user, reminder window (default 30 days), archive flag. Tracking only: no premium/claim accounting.
- Computed state (not stored, evaluated against today): upcoming / active / expiring (end date within the record's own window) / expired, plus days left; searchable (`state = / in`). Bug found by a test and fixed: combining several states built an invalid prefix domain; now uses `expression.OR`.
- Asset: `warranty_end_date` / `insurance_end_date` = latest end date among coverages in force today; coverage tab on the asset form; menu "การรับประกัน/ประกันภัย" (55).
- Reminder cron (daily, batch-limited): one activity per record when it enters its window (`reminder_sent` flag; changing `date_end` or the window re-arms it, so a renewal gets a new reminder). Expired and not-yet-started records are not reminded. No responsible user -> a chatter message instead of silently skipping.
- Maintenance: planning/editing a job suggests `warranty_covered` when a warranty covers the planned date (onchange hint only, never forced).
- Dashboard: tiles for expiring (drill-down) and expired coverage. Officer maintains records, users read; company rule.
- DEV tests: 138 run, 0 failed (11 new).
- Open: claim tracking, document attachments beyond chatter, premium/cost tracking, a standalone expiry report beyond the filtered list, browser UI unchecked, prod not deployed. Phase 2 feature set (transfer, audit/QR, maintenance, warranty) is now built on DEV.

## 27. Phase 3 — reconciliation, roll-forward, ageing, forecast (2026-10-30)

- Shared read-only engine `services/ledger.py` (ORM only, no SQL; GL via `read_group`). Convention used by every report: an asset is on the books at date D when capitalized (or later disposed), in-service date <= D, and no POSTED disposal dated <= D. Cost = `gross_cost`. Accumulated depreciation = posted lines whose entry date <= D minus lines whose reversal is also <= D. Planned/exception lines are never counted as posted (shown separately as "due, not posted").
- **Asset-to-GL reconciliation** (wizard, accountant group, menu Reports): per cost account and per accumulated-depreciation account (from category config): GL balance vs subledger, variance, unposted-due plan, asset count; NBV totals (cost - accumulated; impairment is not modeled = 0); assets whose category has no accounts are listed separately, not silently dropped. Drill-down buttons: GL move lines (posted, <= date) and the assets in the row.
- **Roll-forward** by category for a period: opening cost, additions (by in-service date), disposals, closing; opening accumulated, depreciation (by entry date, net of reversals), disposal write-off, closing; built from the same ledger so two check columns (cost_check, accum_check) are zero by construction (tested incl. disposal).
- **Ageing**: buckets by years since in-service date (<1, 1-3, 3-5, 5-10, >10) with count, cost, posted accumulated, NBV and drill-down; open to all asset users.
- **Depreciation forecast**: pivot/graph/list of not-yet-posted periods (planned + exception) by month.
- DEV tests: 147 run, 0 failed (10 new: GL match with unposted plan shown separately, variance + drill-down, disposal + reversal legs, unmapped category, permissions, roll-forward identities incl. disposal, ageing buckets, forecast domain). Two earlier failures were test bugs (owner's real asset polluting totals; duplicate account codes), fixed in the tests.
- DEV real-data run (read-only, rolled back) on the owner's AST/00461: NBV variance -48,958.33. Cost 122000 GL 0 vs 50,000 (asset is register-only, no cost entry in the GL); accumulated account 12300 GL 0 vs 1,041.67 posted — the posted depreciation entry landed on an account that is no longer the category's accumulated account, so the report flags it. Expected behaviour, and a useful catch.
- Limits: mapping uses the CURRENT category accounts, not the accounts on each historical entry; if a category's accounts change after posting, old entries stay on the old account and show as variance until reclassified. Cost GL is not split by source (opening balances, bills, adjustments) — variance is a prompt to investigate, drill-down shows the lines. Additions use the in-service date, not the bill date. No multi-currency/second-company test (DEV cannot create a company). No printable PDF versions; screens only. Not browser-checked; prod not deployed.
