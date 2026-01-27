from odoo import models, fields

class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    currency_rate = fields.Float(string='Currency Rate (THB/USD)', default=1.0, digits=(12, 6))

class StockLandedCostLines(models.Model):
    _inherit = 'stock.landed.cost.lines'

    cost_line_type = fields.Selection([
        ('expense', 'Expense'),
        ('labor', 'Labor'),
        ('tax', 'Tax'),
        ('transit', 'Transit')
    ], string='Cost Line Type', default='expense')
