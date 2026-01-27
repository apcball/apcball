from odoo import models, fields, tools

class BuzLandedCostReport(models.Model):
    _name = 'buz.landed.cost.report'
    _description = 'Landed Cost Report Summary'
    _auto = False
    _rec_name = 'product_id'
    _order = 'doc_no, product_id'

    # Composite Primary Key representation? No, we use Min ID.
    
    doc_no = fields.Char(readonly=True)
    date = fields.Date(readonly=True)
    ref_no = fields.Char(readonly=True)

    product_id = fields.Many2one('product.product', readonly=True)
    product_categ_id = fields.Many2one('product.category', readonly=True)

    qty = fields.Float(readonly=True)
    
    # Base Cost Info
    price_unit_usd = fields.Float(string='Price/Unit USD', readonly=True)
    cost_usd = fields.Float(string='Cost USD (Base)', readonly=True)
    rate = fields.Float(string='Rate', readonly=True)

    # Landed Cost Info (Allocated)
    total_expense_thb = fields.Float(string='Total Expense THB', readonly=True)
    
    # Final Totals
    total_cost_thb = fields.Float(string='Total Cost THB', readonly=True) # Base THB + Expense THB
    unit_cost_thb = fields.Float(string='Unit Cost THB', readonly=True) # Total THB / Qty

    landed_cost_id = fields.Many2one('stock.landed.cost', readonly=True)
    inventory_name = fields.Char(readonly=True)

    # Relation for drill down
    detail_ids = fields.One2many('buz.landed.cost.report.detail', 'summary_id', string='Cost Lines')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW buz_landed_cost_report AS (
                SELECT
                    MIN(sval.id) AS id, -- Use Min ID as representative
                    lc.name AS doc_no,
                    p.date_done::date AS date,
                    p.origin AS ref_no,

                    sm.product_id,
                    pt.categ_id AS product_categ_id,
                    sval.cost_id AS landed_cost_id,
                    p.name AS inventory_name,

                    sm.quantity AS qty,
                    sm.price_unit AS price_unit_usd,
                    (sm.quantity * sm.price_unit) AS cost_usd,

                    -- Rate (Same logic)
                    COALESCE(NULLIF(lc.currency_rate, 1.0), (1.0 / NULLIF(rcr.rate, 0)), 1.0) AS rate,

                    -- Total Expense (Sum of all cost lines for this move) * Rate
                    SUM(COALESCE(sval.additional_landed_cost, 0)) * COALESCE(NULLIF(lc.currency_rate, 1.0), (1.0 / NULLIF(rcr.rate, 0)), 1.0) AS total_expense_thb,

                    -- Total Cost THB = (Base USD * Rate) + (Total Expense THB)
                    (
                        (sm.quantity * sm.price_unit * COALESCE(NULLIF(lc.currency_rate, 1.0), (1.0 / NULLIF(rcr.rate, 0)), 1.0)) 
                        + 
                        (SUM(COALESCE(sval.additional_landed_cost, 0)) * COALESCE(NULLIF(lc.currency_rate, 1.0), (1.0 / NULLIF(rcr.rate, 0)), 1.0))
                    ) AS total_cost_thb,

                    -- Unit Cost THB
                    CASE WHEN sm.quantity != 0 THEN
                        (
                            (sm.quantity * sm.price_unit * COALESCE(NULLIF(lc.currency_rate, 1.0), (1.0 / NULLIF(rcr.rate, 0)), 1.0)) 
                            + 
                            (SUM(COALESCE(sval.additional_landed_cost, 0)) * COALESCE(NULLIF(lc.currency_rate, 1.0), (1.0 / NULLIF(rcr.rate, 0)), 1.0))
                        ) / sm.quantity
                    ELSE 0 END AS unit_cost_thb

                FROM stock_valuation_adjustment_lines sval
                JOIN stock_landed_cost lc ON lc.id = sval.cost_id
                JOIN stock_move sm ON sm.id = sval.move_id
                JOIN stock_picking p ON p.id = sm.picking_id
                JOIN product_product pp ON pp.id = sm.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                
                -- Rate Join
                LEFT JOIN res_currency usd ON usd.name = 'USD'
                LEFT JOIN LATERAL (
                    SELECT rate 
                    FROM res_currency_rate 
                    WHERE currency_id = usd.id 
                    AND company_id = lc.company_id
                    AND name <= lc.date
                    ORDER BY name DESC LIMIT 1
                ) rcr ON TRUE

                GROUP BY 
                    sval.cost_id, 
                    sval.move_id, 
                    p.name, 
                    p.date_done, 
                    p.origin, 
                    sm.product_id, 
                    pt.categ_id, 
                    lc.name,
                    lc.currency_rate,
                    rcr.rate,
                    sm.quantity,
                    sm.price_unit,
                    sm.id
            )
        """)

class BuzLandedCostReportDetail(models.Model):
    _name = 'buz.landed.cost.report.detail'
    _description = 'Landed Cost Report Detail'
    _auto = False
    
    summary_id = fields.Many2one('buz.landed.cost.report', readonly=True) # Link to summary

    doc_no = fields.Char(readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)

    landed_cost_id = fields.Many2one('stock.landed.cost', readonly=True)
    
    cost_line_name = fields.Char(readonly=True)
    account_code = fields.Char(readonly=True)
    account_name = fields.Char(readonly=True)

    amount_thb = fields.Float(string='Amount THB', readonly=True) # Split cost for this line

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW buz_landed_cost_report_detail AS (
                SELECT
                    sval.id AS id,
                    
                    -- We need a way to link to the Summary View ID. 
                    -- The Summary ID is MIN(sval.id) over the group.
                    -- This is tricky in a view without a subquery or window function.
                    -- Alternative: Join back to the group query? 
                    -- EASIER: The 'summary_id' in One2many doesn't strictly need to be a foreign key constraint in a View. 
                    -- But Odoo needs to be able to search `summary_id` = X.
                    -- If Summary ID = MIN(sval.id) of the group, then Detail records need that ID as a column.
                    
                    (
                        SELECT MIN(s2.id) 
                        FROM stock_valuation_adjustment_lines s2 
                        WHERE s2.cost_id = sval.cost_id AND s2.move_id = sval.move_id
                    ) AS summary_id,
                    
                    p.name AS doc_no,
                    sm.product_id,
                    sval.cost_id AS landed_cost_id,
                    
                    lcl.name AS cost_line_name,
                    aa.code AS account_code,
                    COALESCE(aa.name->>'th_TH', aa.name->>'en_US') AS account_name,

                    -- Cost Allocated * Rate
                    (COALESCE(sval.additional_landed_cost, 0) * COALESCE(NULLIF(lc.currency_rate, 1.0), (1.0 / NULLIF(rcr.rate, 0)), 1.0)) AS amount_thb

                FROM stock_valuation_adjustment_lines sval
                JOIN stock_landed_cost lc ON lc.id = sval.cost_id
                JOIN stock_move sm ON sm.id = sval.move_id
                JOIN stock_picking p ON p.id = sm.picking_id
                LEFT JOIN stock_landed_cost_lines lcl ON sval.cost_line_id = lcl.id
                LEFT JOIN account_account aa ON lcl.account_id = aa.id
                
                LEFT JOIN res_currency usd ON usd.name = 'USD'
                LEFT JOIN LATERAL (
                    SELECT rate 
                    FROM res_currency_rate 
                    WHERE currency_id = usd.id 
                    AND company_id = lc.company_id
                    AND name <= lc.date
                    ORDER BY name DESC LIMIT 1
                ) rcr ON TRUE
            )
        """)
