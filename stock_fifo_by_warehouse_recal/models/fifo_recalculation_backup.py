# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class FifoRecalculationBackup(models.Model):
    """Snapshot of the layers a repair run is about to change.

    The repair only ever writes remaining_qty / remaining_value, so a restore
    only ever puts those two columns back. Nothing is deleted by the wizard, so
    nothing has to be recreated here — an earlier version recreated missing
    layers with fresh ids, which quietly forked the FIFO queue.
    """
    _name = 'fifo.recalculation.backup'
    _description = 'FIFO Recalculation Backup'
    _order = 'create_date desc'

    name = fields.Char(string='Backup Name', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', string='Company', required=True)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses')
    layer_count = fields.Integer(string='Layer Count', readonly=True)
    state = fields.Selection([
        ('active', 'Active'),
        ('restored', 'Restored'),
        ('expired', 'Expired'),
    ], default='active', string='State')
    line_ids = fields.One2many(
        'fifo.recalculation.backup.line', 'backup_id', string='Backup Lines')
    restore_date = fields.Datetime(string='Restore Date', readonly=True)
    restore_log = fields.Text(readonly=True)

    @api.depends('create_date', 'company_id')
    def _compute_name(self):
        for record in self:
            stamp = (record.create_date.strftime('%Y-%m-%d %H:%M:%S')
                     if record.create_date else 'new')
            record.name = 'Backup %s - %s' % (record.company_id.name, stamp)

    def action_restore(self):
        """Put remaining_qty / remaining_value back exactly as they were."""
        self.ensure_one()

        if self.state != 'active':
            raise UserError(_('This backup has already been restored or expired.'))

        # Counted in SQL, not through line_ids: the lines are written with an
        # INSERT ... SELECT, so a cached recordset can be stale.
        self.env.cr.execute(
            'SELECT count(*) FROM fifo_recalculation_backup_line WHERE backup_id = %s',
            (self.id,))
        line_count = self.env.cr.fetchone()[0]
        if not line_count:
            raise UserError(_('This backup holds no layers.'))

        SVL = self.env['stock.valuation.layer']
        SVL.flush_model(['remaining_qty', 'remaining_value'])
        self.env.cr.execute("""
            UPDATE stock_valuation_layer l
            SET remaining_qty = b.remaining_qty,
                remaining_value = b.remaining_value
            FROM fifo_recalculation_backup_line b
            WHERE b.backup_id = %s AND b.layer_id = l.id
        """, (self.id,))
        restored = self.env.cr.rowcount
        SVL.invalidate_model(['remaining_qty', 'remaining_value'])

        missing = line_count - restored
        log = [
            'Restored %s layers.' % restored,
            'Layers no longer present: %s.' % missing,
        ]
        if missing:
            log.append('Those layers were deleted by something other than this '
                       'wizard, which never deletes. They are not recreated: a '
                       'new id would sit in the wrong place in the FIFO queue.')
        _logger.info('fifo recalculation backup %s restored %s layers (%s missing)',
                     self.id, restored, missing)

        self.write({
            'state': 'restored',
            'restore_date': fields.Datetime.now(),
            'restore_log': '\n'.join(log),
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Rollback Complete'),
                'message': '\n'.join(log),
                'type': 'success' if not missing else 'warning',
                'sticky': True,
            }
        }


class FifoRecalculationBackupLine(models.Model):
    """The pre-repair state of one valuation layer."""
    _name = 'fifo.recalculation.backup.line'
    _description = 'FIFO Recalculation Backup Line'

    backup_id = fields.Many2one(
        'fifo.recalculation.backup', required=True, ondelete='cascade', index=True)
    layer_id = fields.Many2one(
        'stock.valuation.layer', string='Original Layer',
        ondelete='set null', index=True)
    product_id = fields.Many2one('product.product', required=True)
    warehouse_id = fields.Many2one('stock.warehouse')

    # quantity / unit_cost / value are recorded for the audit trail only. The
    # repair never writes them, so a restore never puts them back.
    quantity = fields.Float(digits='Product Unit of Measure')
    unit_cost = fields.Float(digits='Product Price')
    value = fields.Float(digits='Product Price')

    remaining_qty = fields.Float(digits='Product Unit of Measure')
    remaining_value = fields.Float(digits='Product Price')
    stock_move_id = fields.Many2one('stock.move')
    description = fields.Char()
