# BUZ Sales Performance Engine

Odoo 17 module that measures **REAL sales performance** — a sale is recognized as
Actual Sales only when **all** business conditions are satisfied:

1. Sale Order confirmed (`state = sale`)
2. Delivery done (`stock.picking.state = done`)
3. Customer invoice posted (`account.move.state = posted`)

The engine enforces the AND rule at **sale-order-line granularity** through a
summary table, `buz.sales.performance.result`, which the dashboard reads
exclusively. Partial delivery, partial invoicing, returns and credit notes are
all derived from the same single aggregation — no special-case code paths.

## Architecture

```
sale.order ─┐
            ├─→ buz.sales.performance.result  ← dashboard reads ONLY this
stock.picking ─┤     (1 row per sale.order.line that is delivered + invoiced)
account.move ─┘
```

| Component | Model / file | Role |
|-----------|--------------|------|
| Summary table | `buz.sales.performance.result` | Recognized net sales per SOL |
| Target | `buz.sales.performance.target` | Person / team / company targets |
| Recompute hooks | `sale_order.py`, `stock_picking.py`, `account_move.py` | Event-driven incremental update |
| Safety net | `cron_spe_rebuild_all` | Nightly full rebuild |
| Dashboard | `controllers/spe_dashboard_controller.py` + OWL component | All KPIs / charts via `read_group` |

## Recognition rule (the AND)

A `buz.sales.performance.result` row exists for a sale order line **iff**:

- it has `qty_delivered > 0` (done outgoing stock moves minus incoming returns), AND
- it has at least one **posted** `out_invoice` or `out_refund` line linked via
  `account.move.line.sale_line_ids`.

`invoice_amount` = Σ posted `out_invoice` line subtotals.
`refund_amount` = Σ posted `out_refund` line subtotals.
`net_sales`     = `invoice_amount` − `refund_amount`.

| Scenario | Net sales |
|----------|-----------|
| SO 100k, 40% delivered, 40% invoiced (posted) | 40,000 |
| 100% delivered, 20% invoice posted, then 80% posted | 20,000 → 100,000 |
| Full + posted 30% credit note | 70,000 |
| Invoiced but **not** delivered | 0 (not recognized) |
| Return (incoming picking) for 3 of 10 | delivered drops to 7; net unchanged until credit note |

## Recompute

Incremental and synchronous. The single aggregation query in
`buz.sales.performance.result._recompute_for_sol` is invoked from:

- `sale.order._action_confirm` / `button_done`
- `stock.picking.button_validate`
- `account.move.action_post` / `button_cancel`

Only the touched sale order lines re-aggregate (a handful of SQL queries,
regardless of total row count). A nightly cron (`cron_spe_rebuild_all`) and a
manual wizard (`buz.spe.recompute.wizard`) provide a full-rebuild safety net
for missed events or initial install on an existing database.

## Security (3-tier + multi-company)

| Group | Sees |
|-------|------|
| SPE: Own Records | rows where `salesperson_id = user` |
| SPE: Team Lead | own + any row on a team the user is member of |
| SPE: Manager | everything |

A global `ir.rule` enforces `company_id in company_ids` on both result and
target models.

## Dashboard

OWL 2 client action registered as `buz_sales_performance_engine`, reachable
from the **Sales Performance → Dashboard** menu. Built with Chart.js (loaded
from Odoo's bundled `/web/static/lib/Chart/Chart.js` — no new JS dependency).

- **KPI cards**: Target · Actual · Achievement % · Forecast · Invoice · Refund ·
  Delivery % · Remaining · Avg Daily.
- **Charts**: Sales vs Target, Daily / Monthly trends, Delivery trend,
  Invoice vs Credit Note, Top Customers / Products / Salespersons / Teams.
- **Leaderboards**: salesperson ranking, team ranking.
- **Drill-down**: clicking a card opens the underlying invoices / credit notes /
  deliveries / sale orders / results filtered to the same scope.

## Targets

`buz.sales.performance.target` supports person / team / company targets over
daily / monthly / quarterly / yearly periods. Achievement is computed from the
result table via `read_group` (O(log n)), not by re-scanning sale orders.

## Testing

```bash
# Isolated docker test (preferred) - edit command in docker-compose.test.yml
docker compose -f docker-compose.test.yml up --abort-on-container-exit

# DEV only - irreversible side effects on the real DB
ssh root@217.216.32.33 "docker exec odoo odoo -d MOG_DEV \
    -u buz_sales_performance_engine --test-enable --stop-after-init --no-http"
```

Test cases (`tests/test_recognition_rule.py`):

1. No delivery + no invoice → not recognized
2. Delivery only → not recognized
3. Invoice only → not recognized
4. Full delivery + full invoice → net = full
5. Partial delivery + partial invoice → net = partial
6. Progressive partial invoicing → 20% → 100%
7. Credit note reduces net
8. Cancel invoice removes recognition
9. Return reduces delivered qty
10. Multi-company isolation

`tests/test_recompute_events.py` covers event hooks + 3-tier access + target
achievement reading from the result table.
