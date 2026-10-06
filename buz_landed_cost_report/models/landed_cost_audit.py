from odoo import models, fields, tools

from .landed_cost_report_line import LC_STATES


class BuzLandedCostAudit(models.Model):
    """One row per landed cost: header total vs allocation vs valuation layers.

    Odoo capitalises an LC into SVL only for the stock still on hand when the LC
    is validated (remaining_qty / move_qty). The rest ("not capitalised") has
    been consumed already and, under manual_periodic valuation, is booked
    nowhere. Only SVL > LC total is a real defect (over-capitalised).
    """
    _name = 'buz.landed.cost.audit'
    _description = 'Landed Cost Audit'
    _auto = False
    _rec_name = 'name'
    _order = 'date desc, id desc'

    name = fields.Char(string='LC Number', readonly=True)
    landed_cost_id = fields.Many2one('stock.landed.cost', readonly=True)
    date = fields.Date(readonly=True)
    state = fields.Selection(LC_STATES, readonly=True)
    target_model = fields.Char(readonly=True)
    vendor_bill_id = fields.Many2one('account.move', string='Vendor Bill', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)

    amount_total = fields.Float(string='LC Total', readonly=True)
    alloc_total = fields.Float(string='Allocated', readonly=True)
    svl_total = fields.Float(string='SVL Value', readonly=True)
    alloc_diff = fields.Float(string='LC Total - Allocated', readonly=True)
    uncapitalised = fields.Float(
        string='Not Capitalised (consumed before LC)', readonly=True)
    move_count = fields.Integer(string='Moves', readonly=True)
    svl_count = fields.Integer(string='SVL Layers', readonly=True)
    has_account_move = fields.Boolean(string='Has Journal Entry', readonly=True)
    alloc_mismatch = fields.Boolean(string='Allocation Mismatch', readonly=True)
    svl_over = fields.Boolean(string='SVL > LC Total (defect)', readonly=True)
    svl_none = fields.Boolean(string='No SVL created', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW buz_landed_cost_audit AS (
                SELECT
                    lc.id AS id,
                    lc.id AS landed_cost_id,
                    lc.name AS name,
                    lc.date AS date,
                    lc.state AS state,
                    lc.target_model AS target_model,
                    lc.vendor_bill_id AS vendor_bill_id,
                    lc.company_id AS company_id,
                    COALESCE(lc.amount_total, 0) AS amount_total,
                    COALESCE(al.total, 0) AS alloc_total,
                    COALESCE(sv.total, 0) AS svl_total,
                    COALESCE(lc.amount_total, 0) - COALESCE(al.total, 0) AS alloc_diff,
                    COALESCE(lc.amount_total, 0) - COALESCE(sv.total, 0) AS uncapitalised,
                    COALESCE(al.moves, 0) AS move_count,
                    COALESCE(sv.layers, 0) AS svl_count,
                    (lc.account_move_id IS NOT NULL) AS has_account_move,
                    ABS(COALESCE(lc.amount_total, 0) - COALESCE(al.total, 0)) > 0.01 AS alloc_mismatch,
                    (lc.state = 'done'
                     AND COALESCE(sv.total, 0) > COALESCE(lc.amount_total, 0) + 0.01) AS svl_over,
                    (lc.state = 'done' AND COALESCE(sv.layers, 0) = 0
                     AND COALESCE(lc.amount_total, 0) <> 0) AS svl_none
                FROM stock_landed_cost lc
                LEFT JOIN (
                    SELECT cost_id,
                           SUM(additional_landed_cost) AS total,
                           COUNT(DISTINCT move_id) AS moves
                    FROM stock_valuation_adjustment_lines
                    GROUP BY cost_id
                ) al ON al.cost_id = lc.id
                LEFT JOIN (
                    SELECT stock_landed_cost_id AS cost_id,
                           SUM(value) AS total,
                           COUNT(*) AS layers
                    FROM stock_valuation_layer
                    WHERE stock_landed_cost_id IS NOT NULL
                    GROUP BY stock_landed_cost_id
                ) sv ON sv.cost_id = lc.id
            )
        """)
