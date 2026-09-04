from odoo import fields, models


class StockCountAdjustmentMismatch(models.Model):
    _name = 'stock.count.adjustment.mismatch'
    _description = 'Stock Count Adjustment Mismatch'
    _order = 'id'

    adjustment_id = fields.Many2one(
        'stock.count.adjustment', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='adjustment_id.company_id', store=True, index=True)
    product_id = fields.Many2one('product.product', index=True)
    warehouse_id = fields.Many2one('stock.warehouse', index=True)
    svl_id = fields.Many2one('stock.valuation.layer', string='Valuation Layer')
    move_id = fields.Many2one('stock.move', string='Stock Move')
    move_line_id = fields.Many2one(
        'stock.move.line', string='Suspect Move Line')

    svl_qty = fields.Float(digits='Product Unit of Measure')
    move_net_qty = fields.Float(digits='Product Unit of Measure')
    diff = fields.Float(digits='Product Unit of Measure')

    suggested_location_id = fields.Many2one(
        'stock.location', string='Suggested Location',
        help="Best guess (the pair's lot_stock_id). Shown, not auto-applied.")

    state = fields.Selection(
        [('open', 'Open'),
         ('fixed', 'Fixed'),
         ('ignored', 'Ignored')],
        default='open', required=True, copy=False)
