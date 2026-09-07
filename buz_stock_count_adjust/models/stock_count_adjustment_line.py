from odoo import api, fields, models


class StockCountAdjustmentLine(models.Model):
    _name = 'stock.count.adjustment.line'
    _description = 'Stock Count Adjustment Line'
    _order = 'product_id, warehouse_id, bucket_seq, id'
    _check_company_auto = True

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

    _sql_constraints = [
        ('bucket_seq_unique',
         'unique(adjustment_id, product_id, warehouse_id, bucket_seq)',
         'Bucket sequence must be unique per product/warehouse in a document.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        self.env['stock.count.adjustment'].browse([
            v['adjustment_id'] for v in vals_list if v.get('adjustment_id')
        ])._check_inputs_editable()
        lines = super().create(vals_list)
        # Also cover adjustment_id supplied by default_get/context.
        lines.adjustment_id._check_inputs_editable()
        lines.adjustment_id._reset_hash_if_changed()
        return lines

    def write(self, vals):
        docs = self.adjustment_id
        if {'adjustment_id', 'product_id', 'warehouse_id', 'bucket_seq',
                'target_qty', 'target_value'} & vals.keys():
            (docs | self.env['stock.count.adjustment'].browse(
                vals.get('adjustment_id', [])))._check_inputs_editable()
        res = super().write(vals)
        (docs | self.adjustment_id)._reset_hash_if_changed()
        return res

    def unlink(self):
        docs = self.adjustment_id
        docs._check_inputs_editable()
        res = super().unlink()
        docs._reset_hash_if_changed()
        return res
