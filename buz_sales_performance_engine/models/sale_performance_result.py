from odoo import api, fields, models


class SalePerformanceResult(models.Model):
    _name = "buz.sales.performance.result"
    _description = "Sales Performance Result (recognized net sales)"
    _order = "date_invoiced desc, date_delivered desc, id desc"
    _check_company_auto = True
    _rec_name = "sale_order_line_id"

    # ------------------------------------------------------------------
    # Dimensions
    # ------------------------------------------------------------------
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True, ondelete="restrict",
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", string="Currency", store=True,
    )
    salesperson_id = fields.Many2one(
        "res.users", string="Salesperson", index=True, ondelete="restrict",
    )
    team_id = fields.Many2one(
        "crm.team", string="Sales Team", index=True, ondelete="restrict",
    )
    partner_id = fields.Many2one(
        "res.partner", string="Customer", index=True, ondelete="restrict",
    )
    product_id = fields.Many2one(
        "product.product", string="Product", index=True, ondelete="restrict",
    )
    categ_id = fields.Many2one(
        "product.category", string="Product Category", index=True, ondelete="restrict",
    )
    sale_order_id = fields.Many2one(
        "sale.order", string="Sale Order", index=True, ondelete="cascade",
    )
    sale_order_line_id = fields.Many2one(
        "sale.order.line", string="Sale Order Line", index=True, ondelete="cascade",
    )

    # ------------------------------------------------------------------
    # Measures (company-currency, signed - refunds are negative on net)
    # ------------------------------------------------------------------
    invoice_amount = fields.Monetary(
        string="Invoice Amount", currency_field="currency_id",
        group_operator="sum",
    )
    refund_amount = fields.Monetary(
        string="Refund Amount", currency_field="currency_id",
        group_operator="sum",
        help="Posted customer credit notes linked to this line (positive value).",
    )
    net_sales = fields.Monetary(
        string="Net Sales", currency_field="currency_id",
        compute="_compute_net_sales", store=True,
        group_operator="sum",
    )
    delivered_qty = fields.Float(string="Delivered Qty", group_operator="sum")
    invoiced_qty = fields.Float(string="Invoiced Qty", group_operator="sum")
    ordered_qty = fields.Float(string="Ordered Qty", group_operator="sum")
    delivery_ratio = fields.Float(
        string="Delivery %", compute="_compute_ratios", store=True,
        group_operator="avg",
    )
    invoice_ratio = fields.Float(
        string="Invoice %", compute="_compute_ratios", store=True,
        group_operator="avg",
    )

    # ------------------------------------------------------------------
    # Time buckets (denormalized for fast read_group on the dashboard)
    # ------------------------------------------------------------------
    date_order = fields.Datetime(string="Order Date", index=True)
    date_delivered = fields.Datetime(string="Delivery Date", index=True)
    date_invoiced = fields.Datetime(string="Invoice Date", index=True)
    period = fields.Selection(
        [
            ("daily", "Daily"),
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("yearly", "Yearly"),
        ],
        string="Period", index=True,
    )
    year = fields.Integer(index=True)
    month = fields.Integer(index=True)
    quarter = fields.Integer(index=True)

    # ------------------------------------------------------------------
    # Computed measures
    # ------------------------------------------------------------------
    @api.depends("invoice_amount", "refund_amount")
    def _compute_net_sales(self):
        for rec in self:
            rec.net_sales = rec.invoice_amount - rec.refund_amount

    @api.depends("delivered_qty", "invoiced_qty", "ordered_qty")
    def _compute_ratios(self):
        for rec in self:
            ordered = rec.ordered_qty or 0.0
            rec.delivery_ratio = (rec.delivered_qty / ordered) if ordered else 0.0
            rec.invoice_ratio = (rec.invoiced_qty / ordered) if ordered else 0.0

    _sql_constraints = [
        (
            "uniq_sol_company",
            "UNIQUE(sale_order_line_id, company_id)",
            "A performance result already exists for this sale order line.",
        ),
    ]

    # ------------------------------------------------------------------
    # Incremental recompute - the heart of the engine.
    # Called from stock.picking / account.move / sale.order hooks.
    # ------------------------------------------------------------------
    @api.model
    def _recompute_for_sol(self, sale_order_line_ids):
        """Re-aggregate performance rows for the given sale order lines.

        One SQL aggregation + upsert per call, regardless of row count.
        A row is created only when the strict AND rule is satisfied:
        the sale order line has *delivered* qty (done stock moves) AND
        at least one *posted* invoice / refund line linked to it.
        """
        if not sale_order_line_ids:
            return self.env["buz.sales.performance.result"]
        sale_order_line_ids = tuple(
            int(i) for i in sale_order_line_ids if i
        )
        if not sale_order_line_ids:
            return self.env["buz.sales.performance.result"]

        env = self.env
        # Resolve the account.move.line <-> sale.order.line M2M relation
        # dynamically so the query is robust across Odoo versions / schemas.
        aml_sol_field = env["account.move.line"]._fields["sale_line_ids"]
        rel_table = aml_sol_field.relation
        rel_col_aml = aml_sol_field.column1  # side of account.move.line
        rel_col_sol = aml_sol_field.column2  # side of sale.order.line
        query = """
            WITH sol AS (
                SELECT
                    sol.id                       AS sol_id,
                    sol.order_id,
                    sol.product_id,
                    sol.product_uom_qty          AS ordered_qty,
                    sol.qty_delivered,
                    sol.qty_invoiced,
                    sol.company_id,
                    so.partner_id,
                    so.user_id                   AS salesperson_id,
                    so.team_id,
                    so.date_order,
                    pt.categ_id
                FROM sale_order_line sol
                JOIN sale_order so ON so.id = sol.order_id
                LEFT JOIN product_product pp ON pp.id = sol.product_id
                LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE sol.id IN %s
                  AND sol.display_type IS NULL
            ),
            posted_aml AS (
                SELECT
                    link.""" + rel_col_sol + """      AS sale_line_id,
                    SUM(CASE WHEN am.move_type = 'out_invoice'
                             THEN aml.price_subtotal ELSE 0 END)   AS invoice_amount,
                    SUM(CASE WHEN am.move_type = 'out_refund'
                             THEN -aml.price_subtotal ELSE 0 END)  AS refund_amount_signed,
                    MAX(am.invoice_date)                          AS date_invoiced
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                JOIN """ + rel_table + """ link ON link.""" + rel_col_aml + """ = aml.id
                WHERE am.state = 'posted'
                  AND am.move_type IN ('out_invoice', 'out_refund')
                GROUP BY link.""" + rel_col_sol + """
            ),
            done_moves AS (
                SELECT
                    sm.sale_line_id,
                    MAX(sp.date_done) AS date_delivered
                FROM stock_move sm
                JOIN stock_picking sp ON sp.id = sm.picking_id
                WHERE sm.state = 'done'
                  AND sm.sale_line_id IS NOT NULL
                GROUP BY sm.sale_line_id
            )
            SELECT
                sol.sol_id,
                sol.order_id,
                sol.product_id,
                sol.ordered_qty,
                COALESCE(sol.qty_delivered, 0.0) AS delivered_qty,
                COALESCE(sol.qty_invoiced, 0.0)  AS invoiced_qty,
                sol.company_id,
                sol.partner_id,
                sol.salesperson_id,
                sol.team_id,
                sol.date_order,
                sol.categ_id,
                COALESCE(aml.invoice_amount, 0.0)         AS invoice_amount,
                COALESCE(-aml.refund_amount_signed, 0.0)  AS refund_amount,
                aml.date_invoiced,
                dm.date_delivered
            FROM sol
            LEFT JOIN posted_aml aml ON aml.sale_line_id = sol.sol_id
            LEFT JOIN done_moves dm  ON dm.sale_line_id  = sol.sol_id
            WHERE COALESCE(sol.qty_delivered, 0.0) > 0
              AND aml.sale_line_id IS NOT NULL
        """
        env.cr.execute(query, (sale_order_line_ids,))
        rows = env.cr.dictfetchall()

        # Drop rows that no longer satisfy the AND rule.
        keep_sol_ids = [r["sol_id"] for r in rows]
        env.cr.execute(
            """
            DELETE FROM buz_sales_performance_result
            WHERE sale_order_line_id IN %s
              AND sale_order_line_id NOT IN %s
            """,
            (sale_order_line_ids, tuple(keep_sol_ids) or (0,)),
        )

        # Upsert the surviving rows.
        existing = {
            r["sale_order_line_id"]: r["id"]
            for r in self.sudo().search_read(
                [("sale_order_line_id", "in", keep_sol_ids)], ["id", "sale_order_line_id"],
            )
        }

        def _period_bucket(dt):
            if not dt:
                return False, 0, 0, 0
            return (
                "monthly",
                dt.year,
                dt.month,
                (dt.month - 1) // 3 + 1,
            )

        vals_list = []
        for row in rows:
            inv_dt = row["date_invoiced"]
            period, year, month, quarter = _period_bucket(inv_dt and fields.Datetime.to_datetime(inv_dt))
            sol_id = row["sol_id"]
            vals = {
                "company_id": row["company_id"],
                "salesperson_id": row["salesperson_id"],
                "team_id": row["team_id"],
                "partner_id": row["partner_id"],
                "product_id": row["product_id"],
                "categ_id": row["categ_id"],
                "sale_order_id": row["order_id"],
                "sale_order_line_id": sol_id,
                "invoice_amount": row["invoice_amount"] or 0.0,
                "refund_amount": row["refund_amount"] or 0.0,
                "delivered_qty": row["delivered_qty"] or 0.0,
                "invoiced_qty": row["invoiced_qty"] or 0.0,
                "ordered_qty": row["ordered_qty"] or 0.0,
                "date_order": row["date_order"],
                "date_delivered": row["date_delivered"],
                "date_invoiced": inv_dt,
                "period": period,
                "year": year,
                "month": month,
                "quarter": quarter,
            }
            if sol_id in existing:
                self.browse(existing[sol_id]).sudo().write(vals)
            else:
                vals_list.append(vals)

        if vals_list:
            self.sudo().create(vals_list)
        return self

    @api.model
    def _recompute_for_orders(self, sale_order_ids):
        """Recompute performance for every line of the given sale orders."""
        if not sale_order_ids:
            return self.env["buz.sales.performance.result"]
        sol_ids = self.env["sale.order.line"].search(
            [("order_id", "in", list(sale_order_ids)), ("display_type", "=", False)]
        ).ids
        return self._recompute_for_sol(sol_ids)

    @api.model
    def _cron_rebuild_all(self, batch_size=500):
        """Full rebuild - safety net for missed events.

        Iterates all sale order lines in batches to avoid memory spikes.
        """
        self.sudo().search([]).unlink()
        domain = [("display_type", "=", False)]
        total = self.env["sale.order.line"].search_count(domain)
        offset = 0
        while offset < total:
            sol_ids = self.env["sale.order.line"].search(
                domain, offset=offset, limit=batch_size
            ).ids
            self._recompute_for_sol(sol_ids)
            offset += batch_size
        return True

    # ------------------------------------------------------------------
    # Drill-down actions
    # ------------------------------------------------------------------
    def action_open_invoices(self):
        self.ensure_one()
        return self._action_for_sol("account.move", [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("line_ids.sale_line_ids", "=", self.sale_order_line_id.id),
        ], name="Posted Invoices", ctx={"default_move_type": "out_invoice"})

    def action_open_credit_notes(self):
        self.ensure_one()
        return self._action_for_sol("account.move", [
            ("move_type", "=", "out_refund"),
            ("state", "=", "posted"),
            ("line_ids.sale_line_ids", "=", self.sale_order_line_id.id),
        ], name="Credit Notes", ctx={"default_move_type": "out_refund"})

    def action_open_deliveries(self):
        self.ensure_one()
        return self._action_for_sol("stock.picking", [
            ("state", "=", "done"),
            ("move_ids.sale_line_id", "=", self.sale_order_line_id.id),
        ], name="Deliveries")

    def action_open_sale_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Sale Order",
            "res_model": "sale.order",
            "res_id": self.sale_order_id.id,
            "view_mode": "form",
        }

    def _action_for_sol(self, res_model, domain, name, ctx=None):
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": res_model,
            "view_mode": "tree,form",
            "domain": domain,
            "context": ctx or {},
        }
