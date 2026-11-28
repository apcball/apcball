"""SQL of the dashboard view: one row per sale order, per POS invoice, per
credit note deducted from a sale order, and per other posted customer invoice.

No Odoo imports, so the same query can be run read-only against a copy of the
database to reconcile it.
"""

DEFAULT_EXCLUDED_SQL = (
    "SELECT id FROM product_product WHERE exclude_from_sales_dashboard")
# "billed so far" for the credit note deduction: today in Thailand
DEFAULT_TODAY_SQL = "(now() AT TIME ZONE 'Asia/Bangkok')::date"

_QUERY = """
WITH RECURSIVE
excluded(id) AS (
    %(excluded)s
),
pos_seed(id) AS (
    SELECT m.id
      FROM account_move m
     WHERE m.journal_id IN (SELECT sale_journal_id FROM pos_lite_config
                             WHERE sale_journal_id IS NOT NULL)
        OR m.name ~ '^(POS|CNP)'
        OR m.invoice_origin LIKE 'POS%%'
        OR (m.move_type = 'out_refund' AND m.ref ~ 'POS[0-9]')
    UNION
    SELECT invoice_id FROM pos_lite_order WHERE invoice_id IS NOT NULL
    UNION
    -- invoices of the former POS flow, which created sale orders named POS...
    SELECT aml.move_id
      FROM sale_order so
      JOIN sale_order_line sol ON sol.order_id = so.id
      JOIN sale_order_line_invoice_rel rel ON rel.order_line_id = sol.id
      JOIN account_move_line aml ON aml.id = rel.invoice_line_id
     WHERE so.name LIKE 'POS%%'
),
pos_move(id) AS (
    SELECT m.id
      FROM pos_seed s
      JOIN account_move m ON m.id = s.id
     WHERE m.move_type IN ('out_invoice', 'out_refund')
    UNION
    -- reversals of a POS document, followed as a chain
    SELECT m.id
      FROM pos_move p
      JOIN account_move m ON m.reversed_entry_id = p.id
     WHERE m.move_type IN ('out_invoice', 'out_refund')
),
so_line AS (
    SELECT l.order_id,
           l.price_subtotal AS untaxed,
           l.price_total AS taxed,
           CASE
               WHEN l.product_uom_qty <= 0 OR l.price_subtotal < 0 THEN 'adjust'
               WHEN pt.detailed_type = 'service' THEN 'service'
               ELSE 'goods'
           END AS kind,
           LEAST(GREATEST(COALESCE(l.qty_delivered, 0)
                          / NULLIF(l.product_uom_qty, 0), 0), 1) AS ratio,
           -- what keeps the rest of the line undelivered, first match wins
           CASE
               WHEN EXISTS (SELECT 1 FROM stock_move sm
                             WHERE sm.sale_line_id = l.id
                               AND sm.state NOT IN ('done', 'cancel'))
                   THEN 'open'
               WHEN COALESCE(l.qty_invoiced, 0) >= l.product_uom_qty - 0.000001
                   THEN 'billed'
               ELSE 'other'
           END AS waiting
      FROM sale_order_line l
      LEFT JOIN product_product pp ON pp.id = l.product_id
      LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
     WHERE l.product_id IS NULL
        OR l.product_id NOT IN (SELECT id FROM excluded)
),
-- Credit notes outside POS that lower a sale order -------------------------
credit_link AS (
    -- each credit note line once, even when linked to several order lines
    SELECT aml.id AS line_id, MIN(so.id) AS order_id
      FROM sale_order so
      JOIN sale_order_line sol ON sol.order_id = so.id
      JOIN sale_order_line_invoice_rel rel ON rel.order_line_id = sol.id
      JOIN account_move_line aml ON aml.id = rel.invoice_line_id
      JOIN account_move m ON m.id = aml.move_id
     WHERE so.state = 'sale'
       AND so.name NOT LIKE 'POS%%'
       AND so.name NOT LIKE '%%ยกเลิก%%'
       AND sol.price_subtotal >= 0
       AND sol.product_uom_qty > 0
       AND (sol.product_id IS NULL
            OR sol.product_id NOT IN (SELECT id FROM excluded))
       AND m.move_type = 'out_refund'
       AND m.state = 'posted'
       AND aml.price_subtotal > 0
       AND m.invoice_date <= %(today)s
       AND m.name NOT LIKE '%%ยกเลิก%%'
       -- NOT EXISTS, not NOT IN: the planner overrates a recursive CTE by far,
       -- and NOT IN then rescans it for every invoice
       AND NOT EXISTS (SELECT 1 FROM pos_move p WHERE p.id = m.id)
     GROUP BY aml.id
),
credit_order_line AS (
    SELECT sol.id, sol.order_id, sol.price_subtotal
      FROM sale_order_line sol
     WHERE sol.order_id IN (SELECT order_id FROM credit_link)
       AND (sol.product_id IS NULL
            OR sol.product_id NOT IN (SELECT id FROM excluded))
),
credit_billed AS (
    -- net posted billing of those order lines, each invoice line once
    SELECT b.order_id, SUM(b.amount) AS billed
      FROM (SELECT DISTINCT sol.order_id, aml.id,
                   aml.price_subtotal * CASE WHEN m.move_type = 'out_refund'
                                             THEN -1 ELSE 1 END AS amount
              FROM credit_order_line sol
              JOIN sale_order_line_invoice_rel rel ON rel.order_line_id = sol.id
              JOIN account_move_line aml ON aml.id = rel.invoice_line_id
              JOIN account_move m ON m.id = aml.move_id
             WHERE m.move_type IN ('out_invoice', 'out_refund')
               AND m.state = 'posted'
               AND m.invoice_date <= %(today)s) b
     GROUP BY b.order_id
),
credit_order AS (
    -- neg: already taken off by negative order lines (oldest notes first)
    -- deduct: the rest, as far as the order has not been billed again
    SELECT t.order_id, t.neg,
           LEAST(GREATEST(c.cand - t.neg, 0),
                 GREATEST(t.net - COALESCE(b.billed, 0), 0)) AS deduct
      FROM (SELECT order_id,
                   SUM(price_subtotal) AS net,
                   COALESCE(-SUM(price_subtotal) FILTER (
                       WHERE price_subtotal < 0), 0) AS neg
              FROM credit_order_line
             GROUP BY order_id) t
      JOIN (SELECT k.order_id, SUM(aml.price_subtotal) AS cand
              FROM credit_link k
              JOIN account_move_line aml ON aml.id = k.line_id
             GROUP BY k.order_id) c ON c.order_id = t.order_id
      LEFT JOIN credit_billed b ON b.order_id = t.order_id
),
credit_running AS (
    SELECT k.order_id, k.line_id, aml.move_id,
           aml.price_subtotal AS untaxed,
           aml.price_total AS taxed,
           COALESCE(SUM(aml.price_subtotal) OVER (
               PARTITION BY k.order_id
               ORDER BY m.invoice_date, m.name, aml.price_subtotal, aml.id
               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS earlier
      FROM credit_link k
      JOIN account_move_line aml ON aml.id = k.line_id
      JOIN account_move m ON m.id = aml.move_id
),
credit_share AS (
    -- the part of each line inside [neg, neg + deduct]
    SELECT r.order_id, r.line_id, r.move_id, r.untaxed, r.taxed,
           GREATEST(LEAST(r.earlier + r.untaxed, o.neg + o.deduct)
                    - GREATEST(r.earlier, o.neg), 0) AS share
      FROM credit_running r
      JOIN credit_order o ON o.order_id = r.order_id
),
pos_document(id) AS (
    -- the POS documents counted in the POS columns
    SELECT m.id
      FROM pos_move p
      JOIN account_move m ON m.id = p.id
     WHERE m.name IS NULL OR m.name NOT LIKE '%%ยกเลิก%%'
),
document AS (
    SELECT so.id * 4 AS id,
           'so'::varchar AS source,
           so.id AS order_id,
           NULL::integer AS move_id,
           so.name::varchar AS name,
           (so.date_order AT TIME ZONE 'UTC'
                          AT TIME ZONE 'Asia/Bangkok')::date AS date,
           so.user_id,
           so.team_id,
           so.company_id,
           (CASE WHEN so.state = 'sale' THEN 'sale'
                 ELSE 'quotation' END)::varchar AS state,
           COALESCE(SUM(l.untaxed) FILTER (WHERE so.state != 'sale'), 0)
               AS amount_quotation,
           COALESCE(SUM(l.untaxed) FILTER (WHERE so.state = 'sale'), 0)
               AS amount_so,
           COALESCE(SUM(l.untaxed * l.ratio) FILTER (
               WHERE so.state = 'sale' AND l.kind = 'goods'), 0)
               AS amount_delivered,
           COALESCE(SUM(l.untaxed * (1 - l.ratio)) FILTER (
               WHERE so.state = 'sale' AND l.kind = 'goods'), 0)
               AS amount_pending,
           COALESCE(SUM(l.untaxed * (1 - l.ratio)) FILTER (
               WHERE so.state = 'sale' AND l.kind = 'goods'
                 AND l.waiting = 'open'), 0) AS amount_pending_open,
           COALESCE(SUM(l.untaxed * (1 - l.ratio)) FILTER (
               WHERE so.state = 'sale' AND l.kind = 'goods'
                 AND l.waiting = 'billed'), 0) AS amount_pending_billed,
           COALESCE(SUM(l.untaxed * (1 - l.ratio)) FILTER (
               WHERE so.state = 'sale' AND l.kind = 'goods'
                 AND l.waiting = 'other'), 0) AS amount_pending_other,
           COALESCE(SUM(l.untaxed) FILTER (
               WHERE so.state = 'sale' AND l.kind = 'service'), 0)
               AS amount_service,
           COALESCE(SUM(l.untaxed) FILTER (
               WHERE so.state = 'sale' AND l.kind = 'adjust'), 0)
               AS amount_adjust,
           0::numeric AS amount_so_credit,
           0::numeric AS amount_pos_invoice,
           0::numeric AS amount_pos_refund,
           0::numeric AS amount_pos,
           COALESCE(SUM(l.untaxed) FILTER (WHERE so.state = 'sale'), 0)
               AS amount_total,
           COALESCE(SUM(l.taxed) FILTER (WHERE so.state = 'sale'), 0)
               AS amount_total_vat,
           0::numeric AS amount_inv_so_invoice,
           0::numeric AS amount_inv_so_refund,
           0::numeric AS amount_inv_so,
           0::numeric AS amount_inv_other,
           0::numeric AS amount_invoiced
      FROM sale_order so
      LEFT JOIN so_line l ON l.order_id = so.id
     WHERE so.state IN ('draft', 'sent', 'sale')
       AND so.name NOT LIKE 'POS%%'
       AND so.name NOT LIKE '%%ยกเลิก%%'
     GROUP BY so.id

    UNION ALL

    SELECT m.id * 4 + 1,
           'pos'::varchar,
           NULL::integer,
           m.id,
           m.name::varchar,
           m.invoice_date,
           m.invoice_user_id,
           m.team_id,
           m.company_id,
           (CASE WHEN m.move_type = 'out_refund' THEN 'refund'
                 ELSE 'invoice' END)::varchar,
           -- quotation, so, delivered, pending and its three groups,
           -- service, adjust, so_credit
           0::numeric, 0::numeric, 0::numeric, 0::numeric, 0::numeric,
           0::numeric, 0::numeric, 0::numeric, 0::numeric, 0::numeric,
           -- pos_invoice, pos_refund, pos, total, total_vat
           COALESCE(SUM(l.price_subtotal) FILTER (
               WHERE m.move_type = 'out_invoice'), 0),
           COALESCE(-SUM(l.price_subtotal) FILTER (
               WHERE m.move_type = 'out_refund'), 0),
           COALESCE(SUM(l.price_subtotal), 0)
               * CASE WHEN m.move_type = 'out_refund' THEN -1 ELSE 1 END,
           COALESCE(SUM(l.price_subtotal), 0)
               * CASE WHEN m.move_type = 'out_refund' THEN -1 ELSE 1 END,
           COALESCE(SUM(l.price_total), 0)
               * CASE WHEN m.move_type = 'out_refund' THEN -1 ELSE 1 END,
           -- invoicing: a POS document counts only in the overall invoiced, in
           -- company currency as Invoice Analysis does
           0::numeric, 0::numeric, 0::numeric, 0::numeric,
           COALESCE(SUM(-l.balance) FILTER (WHERE l.account_id IS NOT NULL), 0)
      FROM account_move m
      LEFT JOIN account_move_line l
             ON l.move_id = m.id
            AND l.display_type = 'product'
            AND (l.product_id IS NULL
                 OR l.product_id NOT IN (SELECT id FROM excluded))
     WHERE m.state = 'posted'
       AND m.id IN (SELECT id FROM pos_document)
     GROUP BY m.id

    UNION ALL

    -- dated by the credit note, owned by the order's salesperson and team
    SELECT MIN(s.line_id) * 4 + 2,
           'so'::varchar,
           so.id,
           m.id,
           m.name::varchar,
           m.invoice_date,
           so.user_id,
           so.team_id,
           so.company_id,
           'so_credit'::varchar,
           -- quotation, so
           0::numeric, -SUM(s.share),
           -- delivered, pending and its three groups, service, adjust
           0::numeric, 0::numeric, 0::numeric, 0::numeric, 0::numeric,
           0::numeric, 0::numeric,
           -- so_credit, pos_invoice, pos_refund, pos, total, total_vat
           -SUM(s.share), 0::numeric, 0::numeric, 0::numeric, -SUM(s.share),
           -SUM(s.share * COALESCE(s.taxed / NULLIF(s.untaxed, 0), 1)),
           0::numeric, 0::numeric, 0::numeric, 0::numeric, 0::numeric
      FROM credit_share s
      JOIN sale_order so ON so.id = s.order_id
      JOIN account_move m ON m.id = s.move_id
     WHERE s.share > 0.005
     GROUP BY so.id, m.id

    UNION ALL

    -- Invoicing outside POS, on the basis of Invoice Analysis: posted customer
    -- invoices and credit notes, minus the balance of their product lines, by
    -- invoice date, invoice salesperson and invoice team.
    SELECT m.id * 4 + 3,
           'so'::varchar,
           NULL::integer,
           m.id,
           m.name::varchar,
           m.invoice_date,
           m.invoice_user_id,
           m.team_id,
           m.company_id,
           (CASE WHEN m.move_type = 'out_refund' THEN 'bill_refund'
                 ELSE 'bill_invoice' END)::varchar,
           -- none of the sales columns
           0::numeric, 0::numeric, 0::numeric, 0::numeric, 0::numeric,
           0::numeric, 0::numeric, 0::numeric, 0::numeric, 0::numeric,
           0::numeric, 0::numeric, 0::numeric, 0::numeric, 0::numeric,
           COALESCE(SUM(-l.balance) FILTER (
               WHERE link.id IS NOT NULL AND m.move_type = 'out_invoice'), 0),
           COALESCE(SUM(-l.balance) FILTER (
               WHERE link.id IS NOT NULL AND m.move_type = 'out_refund'), 0),
           COALESCE(SUM(-l.balance) FILTER (WHERE link.id IS NOT NULL), 0),
           COALESCE(SUM(-l.balance) FILTER (WHERE link.id IS NULL), 0),
           COALESCE(SUM(-l.balance), 0)
      FROM account_move m
      JOIN account_move_line l
        ON l.move_id = m.id
       AND l.display_type = 'product'
       AND l.account_id IS NOT NULL
       AND (l.product_id IS NULL
            OR l.product_id NOT IN (SELECT id FROM excluded))
      LEFT JOIN (SELECT DISTINCT invoice_line_id AS id
                   FROM sale_order_line_invoice_rel) link ON link.id = l.id
     WHERE m.state = 'posted'
       AND m.move_type IN ('out_invoice', 'out_refund')
       AND NOT EXISTS (SELECT 1 FROM pos_document p WHERE p.id = m.id)
     GROUP BY m.id
)
SELECT d.*,
       c.currency_id,
       to_char(d.date, 'YYYY-MM')::varchar AS month,
       (to_char(d.date, 'IYYY-"W"IW') || ' ('
        || to_char(d.date - (EXTRACT(ISODOW FROM d.date)::int - 1), 'DD/MM')
        || '-'
        || to_char(d.date - (EXTRACT(ISODOW FROM d.date)::int - 7), 'DD/MM')
        || ')')::varchar AS week
  FROM document d
  JOIN res_company c ON c.id = d.company_id
"""


def report_query(excluded_sql=DEFAULT_EXCLUDED_SQL,
                 today_sql=DEFAULT_TODAY_SQL):
    return _QUERY % {"excluded": excluded_sql, "today": today_sql}
