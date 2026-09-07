import hashlib

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
    stock_fingerprint = fields.Char(readonly=True, copy=False)
    scope_product_ids = fields.Json(readonly=True, copy=False)

    line_count = fields.Integer(compute='_compute_line_count')

    @api.depends('adjustment_id.name', 'create_date')
    def _compute_name(self):
        for rec in self:
            base = rec.adjustment_id.name or 'SCA'
            rec.name = '%s / backup %s' % (base, rec.id or '')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    def _stock_state_fingerprint(self):
        """Conservatively cover all stock activity for the affected products.

        Include row contents and membership, so later inserts, deletions, raw
        SQL changes and reservations are detected even without write_date.
        """
        self.ensure_one()
        self.env.flush_all()
        products = tuple(self.scope_product_ids or [])
        if not products:
            raise UserError(_('Backup has no verified stock scope.'))
        digest = hashlib.sha256()
        for table in ('stock_valuation_layer', 'stock_quant',
                      'stock_move', 'stock_move_line'):
            self.env.cr.execute("""
                SELECT md5(COALESCE(string_agg(md5(to_jsonb(t)::text), ''
                                               ORDER BY t.id), ''))
                FROM %s t
                WHERE t.product_id IN %%s
                  AND (t.company_id = %%s OR t.company_id IS NULL)
            """ % table, (products, self.company_id.id))
            digest.update(self.env.cr.fetchone()[0].encode())
        if 'stock.valuation.layer.usage' in self.env:
            self.env.cr.execute("""
                SELECT md5(COALESCE(string_agg(md5(to_jsonb(u)::text), ''
                                               ORDER BY u.id), ''))
                FROM stock_valuation_layer_usage u
                WHERE EXISTS (
                    SELECT 1 FROM stock_valuation_layer s
                    WHERE s.product_id IN %s AND s.company_id = %s
                      AND s.id IN (u.stock_valuation_layer_id,
                                   u.dest_stock_valuation_layer_id))
            """, (products, self.company_id.id))
            digest.update(self.env.cr.fetchone()[0].encode())
        return digest.hexdigest()

    def _seal_stock_state(self):
        self.ensure_one()
        self.sudo().write({'stock_fingerprint': self._stock_state_fingerprint()})

    def _check_stock_unchanged(self):
        self.ensure_one()
        self.check_access_rights('read')
        self.check_access_rule('read')
        self.adjustment_id._lock_operation()
        self.invalidate_recordset()
        if self.state != 'active':
            raise UserError(_('The backup is no longer active.'))
        if not self.stock_fingerprint:
            raise UserError(_(
                'This legacy backup has no verified post-apply snapshot. '
                'Automatic restore or mismatch fixing is not safe.'))
        if self.stock_fingerprint != self._stock_state_fingerprint():
            raise UserError(_(
                'Stock changed after this adjustment. Restore or mismatch fixing '
                'would overwrite later activity and has been refused.'))

    def action_restore(self):
        """Put every touched row back to its pre-image, in one pass.

        UPDATE-back the pre-existing rows first, then DELETE the rows the engine
        inserted / generated -- doing it the other way round would strand FK
        references. All SVL / quant / move writes go through raw env.cr.execute;
        invalidate_model afterwards. No cr.commit().
        """
        self.ensure_one()
        self._check_stock_unchanged()
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
                unit_cost = b.unit_cost,
                origin_remaining_qty = b.origin_remaining_qty,
                origin_remaining_value = b.origin_remaining_value
            FROM stock_count_adjustment_backup_line b
            WHERE b.backup_id = %s AND b.layer_id = l.id
              AND b.was_inserted = false
        """, (self.id,))
        log.append('SVL rows restored: %s' % cr.rowcount)

        # 2a. Clear stock_fifo_by_location's FIFO-consumption link rows for the
        # inserted layers first -- stock_valuation_layer_usage.stock_valuation_layer_id
        # is ON DELETE RESTRICT and blocks step 2 whenever the run drove a real
        # move (e.g. _quant_adjust's inventory move fires _run_fifo). dest_* is
        # ON DELETE SET NULL but a dangling NULL corrupts origin tracking, so
        # clean both ends.
        cr.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'stock_valuation_layer_usage'
        """)
        if cr.fetchone():
            cr.execute("""
                DELETE FROM stock_valuation_layer_usage
                WHERE stock_valuation_layer_id IN (
                        SELECT layer_id FROM stock_count_adjustment_backup_line
                        WHERE backup_id = %s AND was_inserted IS TRUE)
                   OR dest_stock_valuation_layer_id IN (
                        SELECT layer_id FROM stock_count_adjustment_backup_line
                        WHERE backup_id = %s AND was_inserted IS TRUE)
            """, (self.id, self.id))
            log.append('SVL usage link rows deleted: %s' % cr.rowcount)

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
        if 'stock.valuation.layer.usage' in self.env:
            self.env['stock.valuation.layer.usage'].invalidate_model()

        self.sudo().write({
            'state': 'restored', 'restore_date': fields.Datetime.now(),
            'restore_log': '\n'.join(log)})
        self.adjustment_id.sudo().write({'state': 'rolled_back'})
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
    origin_remaining_qty = fields.Float(digits='Product Unit of Measure')
    origin_remaining_value = fields.Float(digits='Product Price')
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
