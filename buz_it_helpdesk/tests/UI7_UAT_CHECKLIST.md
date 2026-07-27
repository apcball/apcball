# UI-7 UAT Checklist — IT Management Dashboard

สถานะเอกสาร: ยังไม่รับรอง UAT  
ห้ามสรุปว่า UAT ผ่านจนกว่าผู้ตรวจรับจะลงนาม

## Scope

Regression, Security Review และ UAT ของ UI-4 ถึง UI-6 เท่านั้น  
ไม่รวมการเปลี่ยน Business Workflow, UI-7 feature ใหม่ หรือการ Deploy

## Regression and install/upgrade evidence

| Area | Check | Evidence / result | Owner |
|---|---|---|---|
| Helpdesk | Existing ticket create, state transition, dashboard access, drill-down | รัน Odoo runtime test เมื่อ test environment พร้อม | |
| IT Asset | Create/read, company boundary, asset dashboard, action drill-down | รัน Odoo runtime test เมื่อ test environment พร้อม | |
| Renewal | Renewal source record, expiry/severity, company/date filter | รัน Odoo runtime test เมื่อ test environment พร้อม | |
| Dashboard | KPI/chart/list payload, stale response, navigation, XML/OWL/JS | Static checks ผ่าน; runtime pending | |
| Role Matrix | Requester denied; Agent/Manager allowed; manager-only Settings | Runtime pending; server access checks inspected | |
| Multi-company | Current allowed companies only; selected company does not cross boundary | Runtime pending; company domain inspected | |
| RPC payload | No secrets, attachments, chatter, mail body, notification detail | Static payload scan required and recorded below | |
| Install/Upgrade | Install and module upgrade on isolated DB only | Blocked: Docker/Python runtime unavailable | |

## Source-record comparison evidence

Record the same filters in Dashboard and Source screens. Attach screenshots or exported values.

| Widget | Dashboard value | Source model/action | Filter/domain to compare | Evidence |
|---|---:|---|---|---|
| Open Tickets KPI | | it.helpdesk.ticket | Company + create_date range + open domain | |
| SLA Overdue KPI | | it.helpdesk.ticket | Company + SLA overdue domain | |
| Assets In Use KPI | | buz.it.asset | Company + status = in_use | |
| Under Repair KPI | | buz.it.asset | Company + status = repair | |
| Licenses Expiring KPI | | buz.it.asset | asset_type = software_license + expiry range | |
| Created vs Resolved | | it.helpdesk.ticket | create_date / resolved_at by selected period | |
| Ticket Backlog | | it.helpdesk.ticket | Open statuses only; chart domain | |
| Asset Status | | buz.it.asset | Company + status; total and percentages | |
| Recent Tickets | | it.helpdesk.ticket | Deterministic create_date desc, id desc, max 10 | |
| Renewals Due | | buz.it.asset.renewal | Company + effective expiry range, max 10 | |

## Manual UAT steps

- [ ] Agent: Overview, Helpdesk, IT Assets and permitted actions open without AccessError.
- [ ] Manager: manager-only Settings action is visible and opens the existing action.
- [ ] Requester: dashboard endpoint is denied; hidden menu is not treated as security.
- [ ] Switch allowed company and verify every KPI/chart/list changes only to that company.
- [ ] Change From/To filters and compare Dashboard values with Source Records.
- [ ] Click KPI, chart, Recent Ticket row, Renewal row and View-all actions; verify model, record/domain and action.
- [ ] Verify no license key, password, attachment, chatter, mail body or notification detail is visible in RPC/DOM.
- [ ] Keyboard-only pass: Tab order, Enter/Space activation, focus visibility, sidebar collapse.
- [ ] Responsive pass at 1440, 1280, 1024, 768 and 390 px; no unintended horizontal overflow.
- [ ] Verify Helpdesk and IT Asset existing workflows remain unchanged.

## Sign-off

ผู้ตรวจรับ: ____________________  
บทบาท: ________________________  
วันที่: _________________________  
ผลการตรวจรับ:  [ ] Accepted  [ ] Rework required  
ลายเซ็น: _______________________