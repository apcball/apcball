# IT Management Dashboard UAT Checklist

## Scope

Validate the reduced IT Management structure: Helpdesk only.

## Regression and upgrade

| Area | Check | Evidence |
|---|---|---|
| Menu | IT Management shows only Helpdesk | |
| Helpdesk | Helpdesk dashboard, tickets, SLA and Recent Tickets load | |
| Helpdesk | Ticket list, workflow, SLA and settings remain usable | |
| Roles | Requester denied; Agent/Manager allowed; manager Settings preserved | |
| Company filters | Data stays within allowed companies | |
| Upgrade | Asset cleanup completes on an isolated database backup | |

## Source-record checks

| Widget | Source model | Check |
|---|---|---|
| Open Tickets | `it.helpdesk.ticket` | Company/date/open domain matches |
| SLA Overdue | `it.helpdesk.ticket` | Company/date/SLA domain matches |
| Created vs Resolved | `it.helpdesk.ticket` | Daily counts and drill-down domains match |
| Ticket Backlog | `it.helpdesk.ticket` | Open statuses and counts match |
| Recent Tickets | `it.helpdesk.ticket` | Deterministic order, maximum 10 records |

## Manual checks

- [ ] Helpdesk opens for Agent and Manager.
- [ ] Requester cannot access the Helpdesk dashboard endpoint.
- [ ] Asset menu, Asset section, Asset chart and Renewals Due are absent.
- [ ] KPI, chart and ticket-row drill-downs open Helpdesk records only.
- [ ] No secret or attachment/chatter detail is exposed in the Dashboard payload.
- [ ] Keyboard navigation, responsive layout and loading/error states work.
