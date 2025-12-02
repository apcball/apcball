# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import json


class FifoRecalculationBackup(models.Model):
    """Backup of valuation layers before recalculation."""
    _name = 'fifo.recalculation.backup'
    _description = 'FIFO Recalculation Backup'
    _order = 'create_date desc'

    name = fields.Char(
        string='Backup Name',
        compute='_compute_name',
        store=True
    )
    date_from = fields.Datetime(
        string='Date From',
        required=True
    )
    date_to = fields.Datetime(
        string='Date To',
        required=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True
    )
    layer_count = fields.Integer(
        string='Layer Count',
        readonly=True
    )
    state = fields.Selection([
        ('active', 'Active'),
        ('restored', 'Restored'),
        ('expired', 'Expired'),
    ], default='active', string='State')
    line_ids = fields.One2many(
        'fifo.recalculation.backup.line',
        'backup_id',
        string='Backup Lines'
    )
    restore_date = fields.Datetime(
        string='Restore Date',
        readonly=True
    )

    @api.depends('create_date', 'company_id')
    def _compute_name(self):
        for record in self:
            if record.create_date:
                record.name = f"Backup {record.company_id.name} - {record.create_date.strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                record.name = f"Backup {record.company_id.name}"

    def action_restore(self):
        """Restore backed up layers."""
        self.ensure_one()
        
        if self.state != 'active':
            raise UserError(_('This backup has already been restored or expired.'))
        
        log = []
        log.append(f"=== Restoring Backup: {self.name} ===")
        log.append(f"Layers to restore: {len(self.line_ids)}")
        log.append("")
        
        restored_count = 0
        recreated_count = 0
        failed_count = 0
        
        for line in self.line_ids:
            try:
                # Check if layer still exists
                layer = self.env['stock.valuation.layer'].browse(line.layer_id.id)
                if layer.exists():
                    # Restore original values to existing layer
                    layer.write({
                        'quantity': line.quantity,
                        'unit_cost': line.unit_cost,
                        'value': line.value,
                        'remaining_qty': line.remaining_qty,
                        'remaining_value': line.remaining_value,
                    })
                    restored_count += 1
                else:
                    # Layer was deleted, recreate it
                    layer_vals = {
                        'product_id': line.product_id.id,
                        'company_id': self.company_id.id,
                        'warehouse_id': line.warehouse_id.id if line.warehouse_id else False,
                        'quantity': line.quantity,
                        'unit_cost': line.unit_cost,
                        'value': line.value,
                        'remaining_qty': line.remaining_qty,
                        'remaining_value': line.remaining_value,
                        'stock_move_id': line.stock_move_id.id if line.stock_move_id else False,
                        'description': line.description or 'Restored from backup',
                    }
                    new_layer = self.env['stock.valuation.layer'].create(layer_vals)
                    recreated_count += 1
                    log.append(f"  Recreated layer for {line.product_id.display_name} (original ID: {line.layer_id.id}, new ID: {new_layer.id})")
            except Exception as e:
                log.append(f"ERROR restoring layer {line.layer_id.id}: {str(e)}")
                failed_count += 1
        
        log.append("")
        log.append(f"Restored (updated existing): {restored_count} layers")
        log.append(f"Recreated (deleted layers): {recreated_count} layers")
        log.append(f"Failed: {failed_count} layers")
        
        # Update backup state
        self.write({
            'state': 'restored',
            'restore_date': fields.Datetime.now()
        })
        
        # Also delete usage records that were created during recalculation
        # to clean up the audit trail
        if restored_count > 0 or recreated_count > 0:
            # Find usage records created after this backup
            usage_to_delete = self.env['stock.valuation.layer.usage'].search([
                ('create_date', '>', self.create_date),
                ('stock_valuation_layer_id.product_id', 'in', self.line_ids.mapped('product_id').ids),
                ('stock_valuation_layer_id.warehouse_id', 'in', self.line_ids.mapped('warehouse_id').ids),
            ])
            if usage_to_delete:
                log.append(f"Deleted {len(usage_to_delete)} usage records created after backup")
                usage_to_delete.unlink()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Rollback Complete'),
                'message': _('Restored: %d layers\\nRecreated: %d layers\\nFailed: %d') % (restored_count, recreated_count, failed_count),
                'type': 'success' if failed_count == 0 else 'warning',
                'sticky': True,
            }
        }


class FifoRecalculationBackupLine(models.Model):
    """Individual layer backup line."""
    _name = 'fifo.recalculation.backup.line'
    _description = 'FIFO Recalculation Backup Line'

    backup_id = fields.Many2one(
        'fifo.recalculation.backup',
        required=True,
        ondelete='cascade'
    )
    layer_id = fields.Many2one(
        'stock.valuation.layer',
        string='Original Layer',
        required=False,  # Changed to False to allow backup even if layer is deleted
        ondelete='set null',  # Changed to 'set null' to preserve backup if layer is deleted
        index=True
    )
    product_id = fields.Many2one(
        'product.product',
        required=True,
        index=True
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse'
    )
    quantity = fields.Float(
        digits='Product Unit of Measure'
    )
    unit_cost = fields.Float(
        digits='Product Price'
    )
    value = fields.Float(
        digits='Product Price'
    )
    remaining_qty = fields.Float(
        digits='Product Unit of Measure'
    )
    remaining_value = fields.Float(
        digits='Product Price'
    )
    stock_move_id = fields.Many2one(
        'stock.move'
    )
    description = fields.Char()
    layer_data = fields.Text(
        help='JSON data of additional layer information'
    )
