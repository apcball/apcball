# UI-0 Baseline and Interaction Contract

## Phase

UI-0: Baseline และ Interaction Contract

## Scope and guardrails

- ตรวจ baseline ของ Dashboard ปัจจุบันเท่านั้น
- ไม่แก้ production Python, OWL, JavaScript, XML view/menu หรือ CSS
- ไม่เริ่ม UI-1 และไม่เปลี่ยน business workflow

## Baseline status

| Item | Current baseline |
|---|---|
| Client action | `buz_it_helpdesk_dashboard` ผ่าน `action_helpdesk_dashboard_overview` |
| Sections | `overview`, `helpdesk`, `asset` |
| RPC | `it.management.dashboard.get_dashboard_data(section, filters)` |
| Filters | `company_id`, `date_from`, `date_to`; Helpdesk เพิ่ม `team_id`, `assignee_id`, `priority_id`, `category_id` |
| Date semantics | Ticket/asset KPI ใช้ `create_date`; `license_expiring` ใช้ `license_expiry_date` |
| Trend comparison | ยังไม่มี current-vs-previous-period comparison ใน current payload |
| Visual screenshots | Not captured: browser connection unavailable; no visual claim is made |

## Data contract

`it.management.dashboard.get_dashboard_data(section, filters)` รับ section `overview`, `helpdesk`, `asset` และคืน payload ตามตารางนี้:

| Section | Required payload keys | Source |
|---|---|---|
| `overview` | `kpis`, `tickets`, `assets`, `options.companies` | Ticket dashboard + `buz.it.asset` |
| `helpdesk` | `kpis`, `status_overview`, `trend`, filter options, `domain` | `it.helpdesk.ticket.get_dashboard_data()` |
| `asset` | `kpis`, `status`, `types`, `departments`, `repair`, `options.companies` | `buz.it.asset` |

Every KPI/group row retains `code`, `label`, `count`, and (where drill-down exists) `domain`.

## Source Model and Domain matrix

| Widget/code | Source model | Domain | Date field |
|---|---|---|---|
| `open` | `it.helpdesk.ticket` | base company/date + `stage_id.is_closed = False` | `create_date` |
| status KPIs | `it.helpdesk.ticket` | base company/date + mapped stage IDs | `create_date` |
| `sla_overdue` | `it.helpdesk.ticket` | base company/date + `is_overdue = True` | `create_date` |
| `response_sla_overdue` | `it.helpdesk.ticket` | base company/date + `is_response_overdue = True` | `create_date` |
| `in_use` | `buz.it.asset` | base company/date + `status = in_use` | `create_date` |
| `repair` | `buz.it.asset` | base company/date + `status = repair` | `create_date` |
| `license_expiring` | `buz.it.asset` | software license, non-empty expiry within selected dates | `license_expiry_date` |
| grouped rows | respective source model | base domain + grouped field equality | source `create_date` |

`date_to` is inclusive at the contract level and implemented as `< date_to + 1 day` for record-date domains. Company filters are restricted to `env.companies`; an out-of-scope company returns `[('id', '=', 0)]`.

Renewal fixture/source: `buz.it.asset.renewal`. It is not currently exposed in the Dashboard payload; this is a known baseline gap, not a UI-0 implementation.

## Role matrix

| Role | Dashboard | Helpdesk data | Asset/Renewal menus |
|---|---|---|---|
| Requester | No Dashboard menu; endpoint rejected | Requester workflow | Not granted by this module baseline |
| Support Agent | Dashboard visible | Dashboard and ticket operations | Asset User and License Renewals |
| Helpdesk Manager | Dashboard and Settings | Dashboard and management operations | Asset Manager, Renewals, notification config |
| IT Asset User/Manager | Not granted Dashboard endpoint by asset group alone | Not granted by asset group alone | Asset menus according to group |

Endpoint access requires the Helpdesk Agent group; Manager receives it through implied groups.

## Odoo Action/XML ID inventory

| XML ID | Model/domain | Purpose |
|---|---|---|
| `action_helpdesk_dashboard_overview` | `ir.actions.client`, tag `buz_it_helpdesk_dashboard` | Dashboard |
| `action_helpdesk_report` | `it.helpdesk.ticket.report` | Performance Report |
| `action_buz_it_asset_software_licenses` | `buz.it.asset`, software license | Software Licenses |
| `action_buz_it_asset_renewals` | `buz.it.asset.renewal` | License Renewals |
| `action_buz_it_asset_notification_config` | `buz.it.asset.notification.config` | Notification Configuration |
| `action_helpdesk_categories` / `priorities` / `stages` / `tags` / `teams` | Helpdesk configuration models | Settings |
| `action_buz_it_asset_categories` / `action_buz_it_asset_spec_categories` / `action_buz_it_asset_software` | Asset configuration models | Settings |

## Evidence and limitations

- Baseline fixture/test: `tests/test_ui0_dashboard_baseline.py`
- It creates a small Ticket, Software License Asset and Renewal and checks source-record traceability, domains, company isolation, role access and XML IDs.
- Existing Dashboard tests are retained; no production code is changed.
- Screenshots and live visual checks are blocked because the browser connection was unavailable.

## Phase report

Phase: UI-0 Baseline and Interaction Contract
สถานะ: Passed with known issues
ไฟล์ที่แก้: `UI-0_BASELINE_AND_INTERACTION_CONTRACT.md`, `tests/test_ui0_dashboard_baseline.py`, `tests/__init__.py`
Migration impact: None
Tests ที่รัน: Static XML/JS checks and UI-0 baseline test where Odoo test runtime is available
ผลการทดสอบ: Reported separately; static checks do not substitute for live Odoo test evidence
Security checks: Role and multi-company assertions are included in the baseline test
Visual checks: Blocked; no screenshot evidence claimed
Known issues: Renewal is not in current Dashboard payload; trend comparison is not implemented; visual screenshots require browser access
Rollback: Remove the UI-0 document and test/import; no production or database migration changed
งานที่ยังไม่ทำ: UI-1 through UI-7, visual redesign, new KPI/chart/list behavior, deployment and UAT sign-off

หยุดที่ UI-0 และรอผู้ใช้ตรวจรับ
