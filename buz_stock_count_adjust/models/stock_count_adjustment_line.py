from odoo import fields, models


class StockCountAdjustmentLine(models.Model):
    _name = 'stock.count.adjustment.line'
    _description = 'Stock Count Adjustment Line'
    _order = 'product_id, warehouse_id, bucket_seq, id'

    adjustment_id = fields.Many2one(
        'stock.count.adjustment', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='adjustment_id.company_id', store=True, index=True)
    product_id = fields.Many2one(
        'product.product', required=True, index=True, check_company=True)
    warehouse_id = fields.Many2one(
        'stock.warehouse', required=True, index=True, check_company=True)
    bucket_seq = fields.Integer(
        default=10,
        help="Order within a (product, warehouse) group. Step 10. Multiple lines = ordered FIFO buckets.")
    target_qty = fields.Float(digits='Product Unit of Measure')
    target_value = fields.Float(digits='Product Price')
    note = fields.Char()

    baseline_qty = fields.Float(
        digits='Product Unit of Measure', readonly=True, copy=False)
    baseline_value = fields.Float(
        digits='Product Price', readonly=True, copy=False)
    delta_qty = fields.Float(
        digits='Product Unit of Measure', readonly=True, copy=False)
    delta_value = fields.Float(
        digits='Product Price', readonly=True, copy=False)

    state = fields.Selection(
        [('pending', 'Pending'),
         ('previewed', 'Previewed'),
         ('applied', 'Applied'),
         ('skipped', 'Skipped'),
         ('error', 'Error')],
        default='pending', required=True, copy=False)
    result_note = fields.Char(readonly=True, copy=False)
