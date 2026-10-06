from odoo import models, fields, tools

LC_STATES = [('draft', 'Draft'), ('done', 'Posted'), ('cancel', 'Cancelled')]


class BuzLandedCostReport(models.Model):
    """One row per landed cost x stock move (= product line of the receipt).

    All amounts are in company currency. `stock.valuation.adjustment.lines.
    additional_landed_cost` is already company currency, so no FX is applied.
    Base cost comes from the receipt move (price_unit x allocated qty). When
    the move price is demonstrably not converted to company currency (foreign
    PO and move price == PO line price) or is zero, the SVL base value is used
    instead (`base_source` = 'svl'). The LC snapshot (`former_cost`) and the
    SVL values are exposed for comparison.

    Odoo capitalises a landed cost into SVL only for the quantity still on hand
    at validation (remaining_qty / move_qty), so `svl_landed_diff` is the part
    already consumed before the LC, not a defect. See buz.landed.cost.audit.
    """
    _name = 'buz.landed.cost.report'
    _description = 'Landed Cost Report Summary'
    _auto = False
    _rec_name = 'product_id'
    _order = 'doc_no, product_id'

    doc_no = fields.Char(string='LC Number', readonly=True)
    date = fields.Date(string='LC Date', readonly=True)
    receipt_date = fields.Date(string='Receipt Date', readonly=True)
    state = fields.Selection(LC_STATES, readonly=True)
    target_model = fields.Char(readonly=True)
    ref_no = fields.Char(string='Source Doc', readonly=True)
    inventory_name = fields.Char(string='Transfer', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Vendor', readonly=True)
    purchase_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)
    vendor_bill_id = fields.Many2one('account.move', string='Vendor Bill', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)

    product_id = fields.Many2one('product.product', readonly=True)
    product_categ_id = fields.Many2one('product.category', readonly=True)
    landed_cost_id = fields.Many2one('stock.landed.cost', readonly=True)

    qty = fields.Float(string='Qty', readonly=True)
    base_source = fields.Selection(
        [('move', 'Receipt move price'), ('svl', 'Valuation layer (fallback)')],
        string='Base Source', readonly=True)
    base_unit_cost = fields.Float(string='Base Unit Cost', readonly=True)
    base_cost = fields.Float(string='Base Cost', readonly=True)
    landed_cost = fields.Float(string='Landed Amount', readonly=True)
    total_cost = fields.Float(string='Total Cost', readonly=True)
    unit_cost = fields.Float(string='Final Unit Cost', readonly=True)

    expense_amount = fields.Float(string='Expense', readonly=True)
    labor_amount = fields.Float(string='Labor', readonly=True)
    tax_amount = fields.Float(string='Tax', readonly=True)
    transit_amount = fields.Float(string='Transit', readonly=True)

    lc_former_cost = fields.Float(string='LC former_cost (snapshot)', readonly=True)
    svl_base_value = fields.Float(string='SVL Base Value', readonly=True)
    svl_landed_value = fields.Float(string='SVL Landed Value', readonly=True)
    svl_landed_diff = fields.Float(string='Not Capitalised (consumed before LC)', readonly=True)

    detail_ids = fields.One2many('buz.landed.cost.report.detail', 'summary_id', string='Cost Lines')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW buz_landed_cost_report AS (
                SELECT
                    MIN(val.id) AS id,
                    lc.name AS doc_no,
                    lc.date AS date,
                    p.date_done::date AS receipt_date,
                    lc.state AS state,
                    lc.target_model AS target_model,
                    COALESCE(p.origin, sm.reference) AS ref_no,
                    COALESCE(p.name, sm.reference) AS inventory_name,
                    p.partner_id AS partner_id,
                    pol.order_id AS purchase_id,
                    lc.vendor_bill_id AS vendor_bill_id,
                    spt.warehouse_id AS warehouse_id,
                    lc.company_id AS company_id,

                    sm.product_id AS product_id,
                    pt.categ_id AS product_categ_id,
                    lc.id AS landed_cost_id,

                    MAX(val.quantity) AS qty,
                    CASE WHEN (po.currency_id <> cc.currency_id
                                AND pol.price_unit <> 0
                                AND ABS(COALESCE(sm.price_unit, 0) - pol.price_unit) < 0.01
                                OR COALESCE(sm.price_unit, 0) = 0)
                              AND COALESCE(MAX(svb.value), 0) > 0
                        
                         THEN 'svl' ELSE 'move' END AS base_source,
                    CASE WHEN MAX(val.quantity) != 0
                         THEN (CASE WHEN (po.currency_id <> cc.currency_id
                                AND pol.price_unit <> 0
                                AND ABS(COALESCE(sm.price_unit, 0) - pol.price_unit) < 0.01
                                OR COALESCE(sm.price_unit, 0) = 0)
                              AND COALESCE(MAX(svb.value), 0) > 0
                         THEN COALESCE(MAX(svb.value), 0)
                         ELSE MAX(val.quantity) * COALESCE(sm.price_unit, 0) END) / MAX(val.quantity) ELSE 0 END AS base_unit_cost,
                    CASE WHEN (po.currency_id <> cc.currency_id
                                AND pol.price_unit <> 0
                                AND ABS(COALESCE(sm.price_unit, 0) - pol.price_unit) < 0.01
                                OR COALESCE(sm.price_unit, 0) = 0)
                              AND COALESCE(MAX(svb.value), 0) > 0
                         THEN COALESCE(MAX(svb.value), 0)
                         ELSE MAX(val.quantity) * COALESCE(sm.price_unit, 0) END AS base_cost,
                    SUM(COALESCE(val.additional_landed_cost, 0)) AS landed_cost,
                    CASE WHEN (po.currency_id <> cc.currency_id
                                AND pol.price_unit <> 0
                                AND ABS(COALESCE(sm.price_unit, 0) - pol.price_unit) < 0.01
                                OR COALESCE(sm.price_unit, 0) = 0)
                              AND COALESCE(MAX(svb.value), 0) > 0
                         THEN COALESCE(MAX(svb.value), 0)
                         ELSE MAX(val.quantity) * COALESCE(sm.price_unit, 0) END
                        + SUM(COALESCE(val.additional_landed_cost, 0)) AS total_cost,
                    CASE WHEN MAX(val.quantity) != 0 THEN
                        (CASE WHEN (po.currency_id <> cc.currency_id
                                AND pol.price_unit <> 0
                                AND ABS(COALESCE(sm.price_unit, 0) - pol.price_unit) < 0.01
                                OR COALESCE(sm.price_unit, 0) = 0)
                              AND COALESCE(MAX(svb.value), 0) > 0
                         THEN COALESCE(MAX(svb.value), 0)
                         ELSE MAX(val.quantity) * COALESCE(sm.price_unit, 0) END
                         + SUM(COALESCE(val.additional_landed_cost, 0))) / MAX(val.quantity)
                    ELSE 0 END AS unit_cost,

                    COALESCE(SUM(val.additional_landed_cost)
                        FILTER (WHERE COALESCE(lcl.cost_line_type, 'expense') = 'expense'), 0) AS expense_amount,
                    COALESCE(SUM(val.additional_landed_cost)
                        FILTER (WHERE lcl.cost_line_type = 'labor'), 0) AS labor_amount,
                    COALESCE(SUM(val.additional_landed_cost)
                        FILTER (WHERE lcl.cost_line_type = 'tax'), 0) AS tax_amount,
                    COALESCE(SUM(val.additional_landed_cost)
                        FILTER (WHERE lcl.cost_line_type = 'transit'), 0) AS transit_amount,

                    MAX(val.former_cost) AS lc_former_cost,
                    COALESCE(MAX(svb.value), 0) AS svl_base_value,
                    COALESCE(MAX(svl.value), 0) AS svl_landed_value,
                    SUM(COALESCE(val.additional_landed_cost, 0)) - COALESCE(MAX(svl.value), 0)
                        AS svl_landed_diff
                FROM stock_valuation_adjustment_lines val
                JOIN stock_landed_cost lc ON lc.id = val.cost_id
                JOIN stock_move sm ON sm.id = val.move_id
                JOIN product_product pp ON pp.id = sm.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN stock_picking p ON p.id = sm.picking_id
                LEFT JOIN stock_picking_type spt ON spt.id = sm.picking_type_id
                LEFT JOIN purchase_order_line pol ON pol.id = sm.purchase_line_id
                LEFT JOIN purchase_order po ON po.id = pol.order_id
                JOIN res_company cc ON cc.id = lc.company_id
                LEFT JOIN stock_landed_cost_lines lcl ON lcl.id = val.cost_line_id
                LEFT JOIN (
                    SELECT stock_move_id, SUM(value) AS value
                    FROM stock_valuation_layer
                    WHERE stock_landed_cost_id IS NULL
                    GROUP BY stock_move_id
                ) svb ON svb.stock_move_id = sm.id
                LEFT JOIN (
                    SELECT stock_move_id, stock_landed_cost_id, SUM(value) AS value
                    FROM stock_valuation_layer
                    WHERE stock_landed_cost_id IS NOT NULL
                    GROUP BY stock_move_id, stock_landed_cost_id
                ) svl ON svl.stock_move_id = sm.id AND svl.stock_landed_cost_id = lc.id
                GROUP BY
                    lc.id, lc.name, lc.date, lc.state, lc.target_model, lc.vendor_bill_id,
                    lc.company_id, sm.id, sm.product_id, sm.price_unit, sm.reference,
                    pt.categ_id, p.name, p.date_done, p.origin, p.partner_id,
                    pol.order_id, pol.price_unit, po.currency_id, cc.currency_id, spt.warehouse_id
            )
        """)


class BuzLandedCostReportDetail(models.Model):
    _name = 'buz.landed.cost.report.detail'
    _description = 'Landed Cost Report Detail'
    _auto = False
    _order = 'doc_no, id'

    summary_id = fields.Many2one('buz.landed.cost.report', readonly=True)
    doc_no = fields.Char(string='LC Number', readonly=True)
    inventory_name = fields.Char(string='Transfer', readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    landed_cost_id = fields.Many2one('stock.landed.cost', readonly=True)

    cost_line_name = fields.Char(readonly=True)
    cost_line_type = fields.Char(readonly=True)
    split_method = fields.Char(readonly=True)
    account_code = fields.Char(readonly=True)
    account_name = fields.Char(readonly=True)
    amount = fields.Float(string='Allocated Amount', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW buz_landed_cost_report_detail AS (
                SELECT
                    val.id AS id,
                    -- same key as buz_landed_cost_report.id (MIN id of lc x move group)
                    MIN(val.id) OVER (PARTITION BY val.cost_id, val.move_id) AS summary_id,
                    lc.name AS doc_no,
                    COALESCE(p.name, sm.reference) AS inventory_name,
                    sm.product_id AS product_id,
                    val.cost_id AS landed_cost_id,
                    lcl.name AS cost_line_name,
                    COALESCE(lcl.cost_line_type, 'expense') AS cost_line_type,
                    lcl.split_method AS split_method,
                    aa.code AS account_code,
                    COALESCE(aa.name->>'th_TH', aa.name->>'en_US') AS account_name,
                    COALESCE(val.additional_landed_cost, 0) AS amount
                FROM stock_valuation_adjustment_lines val
                JOIN stock_landed_cost lc ON lc.id = val.cost_id
                JOIN stock_move sm ON sm.id = val.move_id
                LEFT JOIN stock_picking p ON p.id = sm.picking_id
                LEFT JOIN stock_landed_cost_lines lcl ON lcl.id = val.cost_line_id
                LEFT JOIN account_account aa ON aa.id = lcl.account_id
            )
        """)
