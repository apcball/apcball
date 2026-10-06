from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    landed_cost_type_id = fields.Many2one(
        'buz.landed.cost.type', string='Landed Cost Type', ondelete='restrict',
        help="Cost type used for this landed cost product on landed cost lines "
             "and in the landed cost reports.")


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    currency_rate = fields.Float(string='Currency Rate (THB/USD)', default=1.0, digits=(12, 6))


class StockLandedCostLines(models.Model):
    _inherit = 'stock.landed.cost.lines'

    # Deprecated: replaced by cost_type_id. Column kept so existing data survives
    # and can be migrated; not shown in views.
    cost_line_type = fields.Selection([
        ('expense', 'Expense'),
        ('labor', 'Labor'),
        ('tax', 'Tax'),
        ('transit', 'Transit')
    ], string='Cost Line Type (legacy)', default='expense')
    cost_type_id = fields.Many2one(
        'buz.landed.cost.type', string='Cost Type',
        compute='_compute_cost_type_id', store=True, readonly=False,
        ondelete='restrict')

    @api.depends('product_id', 'product_id.landed_cost_type_id')
    def _compute_cost_type_id(self):
        Type = self.env['buz.landed.cost.type']
        expense = self.env.ref('buz_landed_cost_report.cost_type_expense', raise_if_not_found=False)
        for line in self:
            legacy = Type.search([('code', '=', line.cost_line_type)], limit=1) \
                if line.cost_line_type else Type
            line.cost_type_id = line.product_id.landed_cost_type_id or legacy or expense
