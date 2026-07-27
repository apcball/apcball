# UI-6 Performance Baseline

Date: 2026-07-27
Scope: IT Management Dashboard UI-6 only.

## Baseline contract

- Overview initial load: one dashboard RPC; list payloads are capped by _LIST_LIMIT = 10 and each requested list limit is clamped to 1..10.
- Section navigation: the selected section is loaded only when selected; Helpdesk remains its existing subcomponent and asset data is not requested for Helpdesk.
- Refresh/filter sequence: each RPC receives a monotonically increasing request sequence; stale responses cannot replace current state, loading, or error state.
- Renewals query: the ORM search uses the bounded list limit and deterministic 
ew_expiry_date asc, id asc ordering; timezone configuration is cached per company within the response.
- Payload safety: dashboard rows contain display/action fields only; no description, attachment, chatter, mail body, or secret fields.

## Repeatable measurement

1. Open Odoo DEV in a clean browser session and enable DevTools Network with cache disabled.
2. Set viewport widths to 1440, 1280, 1024, 768, and 390 px; reload Overview and record RPC count, transferred bytes, response duration, and horizontal overflow.
3. Change Company, From, and To filters quickly; verify only the latest response updates the screen and record the request order.
4. Open Helpdesk and IT Assets separately; confirm section-specific RPCs and compare payload sizes.
5. Request ecent_limit=999 and enewal_limit=999 through the test harness; verify response rows never exceed 10.
6. Run keyboard-only Tab/Shift+Tab, Enter, and Space checks; repeat with prefers-reduced-motion: reduce.

Runtime timing and byte measurements require an Odoo/browser environment; this repository check records the reproducible method and enforceable bounds.
