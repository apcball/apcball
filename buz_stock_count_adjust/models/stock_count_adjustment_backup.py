from odoo import api, fields, models


class StockCountAdjustmentBackup(models.Model):
    _name = 'stock.count.adjustment.backup'
    _description = 'Stock Count Adjustment Backup'
    _order = 'id desc'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)
    adjustment_id = fields.Many2one(
        'stock.count.adjustment', required=True, ondelete='cascade', index=True)
    state = fields.Selection(
        [('active', 'Active'),
         ('restored', 'Restored')],
        default='active', required=True, copy=False)

    line_ids = fields.One2many(
        'stock.count.adjustment.backup.line', 'backup_id', string='SVL Pre-image')
    quant_line_ids = fields.One2many(
        'stock.count.adjustment.backup.quant', 'backup_id', string='Quant Pre-image')
    moveline_line_ids = fields.One2many(
        'stock.count.adjustment.backup.moveline', 'backup_id',
        string='Move Line Pre-image')

    restore_date = fields.Datetime(readonly=True, copy=False)
    restore_log = fields.Text(readonly=True, copy=False)

    @api.depends('adjustment_id.name', 'create_date')
    def _compute_name(self):
        for rec in self:
            base = rec.adjustment_id.name or 'SCA'
            rec.name = '%s / backup %s' % (base, rec.id or '')


class StockCountAdjustmentBackupLine(models.Model):
    _name = 'stock.count.adjustment.backup.line'
    _description = 'Stock Count Adjustment Backup Line (SVL pre-image)'

    backup_id = fields.Many2one(
        'stock.count.adjustment.backup', required=True, ondelete='cascade',
        index=True)
    layer_id = fields.Many2one('stock.valuation.layer', index=True)
    product_id = fields.Many2one('product.product', index=True)
    warehouse_id = fields.Many2one('stock.warehouse', index=True)
    quantity = fields.Float(digits='Product Unit of Measure')
    value = fields.Float(digits='Product Price')
    unit_cost = fields.Float(digits='Product Price')
    remaining_qty = fields.Float(digits='Product Unit of Measure')
    remaining_value = fields.Float(digits='Product Price')
    accounting_date = fields.Datetime()
    was_inserted = fields.Boolean(default=False)


class StockCountAdjustmentBackupQuant(models.Model):
    _name = 'stock.count.adjustment.backup.quant'
    _description = 'Stock Count Adjustment Backup Quant (pre-image)'

    backup_id = fields.Many2one(
        'stock.count.adjustment.backup', required=True, ondelete='cascade',
        index=True)
    quant_id = fields.Many2one('stock.quant')
    quantity = fields.Float(digits='Product Unit of Measure')


class StockCountAdjustmentBackupMoveline(models.Model):
    _name = 'stock.count.adjustment.backup.moveline'
    _description = 'Stock Count Adjustment Backup Move Line (pre-image)'

    backup_id = fields.Many2one(
        'stock.count.adjustment.backup', required=True, ondelete='cascade',
        index=True)
    move_line_id = fields.Many2one('stock.move.line')
    move_id = fields.Many2one('stock.move')
    location_id = fields.Many2one('stock.location')
    location_dest_id = fields.Many2one('stock.location')
    ml_date = fields.Datetime()
    move_date = fields.Datetime()
    was_generated = fields.Boolean(default=False)
