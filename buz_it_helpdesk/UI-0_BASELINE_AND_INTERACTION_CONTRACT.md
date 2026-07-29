# IT Management Dashboard Contract

## Scope

The IT Management main area currently contains only Dashboard and Helpdesk. The Asset subsystem is retired from this addon and is removed from the runtime UI and RPC contract.

## Client and RPC

- Client action: `buz_it_helpdesk_dashboard` through `action_helpdesk_dashboard_overview`
- RPC: `it.management.dashboard.get_dashboard_data(section, filters)`
- Valid sections: `overview`, `helpdesk`
- Filters: `company_id`, `date_from`, `date_to`; Helpdesk-specific filters remain supported by the Helpdesk dashboard
- Access: Helpdesk Agent and Helpdesk Manager; Requester is denied

## Dashboard payload

`overview` returns Helpdesk-only data:

- `kpis`: Open Tickets and SLA Overdue
- `charts.created_resolved`
- `charts.ticket_backlog`
- `recent_tickets`
- `options.companies` and `options.navigation`

`helpdesk` returns the existing Helpdesk dashboard payload and server-provided navigation.

All drill-down records use `it.helpdesk.ticket`. No Asset models, Asset actions, renewal payloads or Asset status charts are part of the contract.

## Menu contract

Under `IT Management`, the only top-level menus are:

- Dashboard
- Helpdesk

Helpdesk retains Tickets, My Tickets, SLA and manager-only Settings.

## Migration

Addon version `17.0.1.4.0` runs an idempotent cleanup function during update. It removes retired Asset records, chatter/attachments, cron, access rules, groups, model metadata and legacy Asset tables. A database backup is required before upgrade.
