from odoo import _, api, fields, models
from odoo.exceptions import UserError


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

    line_count = fields.Integer(compute='_compute_line_count')

    @api.depends('adjustment_id.name', 'create_date')
    def _compute_name(self):
        for rec in self:
            base = rec.adjustment_id.name or 'SCA'
            rec.name = '%s / backup %s' % (base, rec.id or '')

    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    def action_restore(self):
        """Put every touched row back to its pre-image, in one pass.

        UPDATE-back the pre-existing rows first, then DELETE the rows the engine
        inserted / generated -- doing it the other way round would strand FK
        references. All SVL / quant / move writes go through raw env.cr.execute;
        invalidate_model afterwards. No cr.commit().
        """
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_('Backup %s is already %s.') % (self.name, self.state))

        cr = self.env.cr
        SVL = self.env['stock.valuation.layer']
        Quant = self.env['stock.quant']
        Move = self.env['stock.move']
        ML = self.env['stock.move.line']

        SVL.flush_model(['remaining_qty', 'remaining_value', 'value', 'unit_cost'])
        Quant.flush_model(['quantity'])
        ML.flush_model(['location_id', 'location_dest_id', 'date'])
        Move.flush_model(['date'])

        log = []

        # 1. UPDATE-back pre-existing SVL rows (was_inserted = false).
        cr.execute("""
            UPDATE stock_valuation_layer l
            SET remaining_qty = b.remaining_qty,
                remaining_value = b.remaining_value,
                value = b.value,
                unit_cost = b.unit_cost
            FROM stock_count_adjustment_backup_line b
            WHERE b.backup_id = %s AND b.layer_id = l.id
              AND b.was_inserted = false
        """, (self.id,))
        log.append('SVL rows restored: %s' % cr.rowcount)

        # 2. DELETE the layers the engine inserted (was_inserted = true).
        cr.execute("""
            DELETE FROM stock_valuation_layer
            WHERE id IN (
                SELECT layer_id FROM stock_count_adjustment_backup_line
                WHERE backup_id = %s AND was_inserted = true)
        """, (self.id,))
        log.append('Inserted SVL rows deleted: %s' % cr.rowcount)

        # 3. UPDATE-back stock_quant.quantity.
        cr.execute("""
            UPDATE stock_quant q
            SET quantity = b.quantity
            FROM stock_count_adjustment_backup_quant b
            WHERE b.backup_id = %s AND b.quant_id = q.id
        """, (self.id,))
        log.append('Quant rows restored: %s' % cr.rowcount)

        # 4. Restore pre-existing move lines / moves; delete generated ones.
        cr.execute("""
            UPDATE stock_move_line sml
            SET location_id = b.location_id,
                location_dest_id = b.location_dest_id,
                date = b.ml_date
            FROM stock_count_adjustment_backup_moveline b
            WHERE b.backup_id = %s AND b.move_line_id = sml.id
              AND b.was_generated = false
        """, (self.id,))
        log.append('Move lines restored: %s' % cr.rowcount)
        cr.execute("""
            UPDATE stock_move sm
            SET date = b.move_date
            FROM stock_count_adjustment_backup_moveline b
            WHERE b.backup_id = %s AND b.move_id = sm.id
              AND b.was_generated = false
        """, (self.id,))
        log.append('Moves restored: %s' % cr.rowcount)

        cr.execute("""
            SELECT DISTINCT move_id FROM stock_count_adjustment_backup_moveline
            WHERE backup_id = %s AND was_generated = true AND move_id IS NOT NULL
        """, (self.id,))
        gen_move_ids = tuple(r[0] for r in cr.fetchall())
        if gen_move_ids:
            cr.execute("DELETE FROM stock_valuation_layer "
                       "WHERE stock_move_id IN %s", (gen_move_ids,))
            log.append('Generated SVL deleted: %s' % cr.rowcount)
            cr.execute("DELETE FROM stock_move_line WHERE move_id IN %s",
                       (gen_move_ids,))
            log.append('Generated move lines deleted: %s' % cr.rowcount)
            cr.execute("DELETE FROM stock_move WHERE id IN %s", (gen_move_ids,))
            log.append('Generated moves deleted: %s' % cr.rowcount)

        # 5. Drop every stale ORM cache and close out the backup.
        for model in (SVL, Quant, Move, ML):
            model.invalidate_model()

        self.state = 'restored'
        self.restore_date = fields.Datetime.now()
        self.restore_log = '\n'.join(log)
        return True


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
