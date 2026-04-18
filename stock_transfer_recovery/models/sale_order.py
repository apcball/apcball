from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    can_recreate_transfer = fields.Boolean(
        compute='_compute_can_recreate_transfer',
        string='Can Recreate Transfer'
    )

    @api.depends('picking_ids.state', 'order_line.qty_delivered', 'order_line.product_uom_qty')
    def _compute_can_recreate_transfer(self):
        for order in self:
            can_recreate = False
            
            if order.state not in ['sale', 'done']:
                order.can_recreate_transfer = False
                continue

            # Check if any picking is in done and fully matches ordered qty
            all_delivered = all(
                (line.qty_delivered >= line.product_uom_qty if line.product_uom_qty > 0 else line.qty_delivered <= line.product_uom_qty) 
                for line in order.order_line if line.product_uom_qty != 0
            )
            
            if all_delivered:
                order.can_recreate_transfer = False
                continue

            if not order.picking_ids:
                can_recreate = True
            elif all(p.state == 'cancel' for p in order.picking_ids):
                can_recreate = True
            elif any((line.qty_delivered < line.product_uom_qty if line.product_uom_qty > 0 else line.qty_delivered > line.product_uom_qty) for line in order.order_line if line.product_uom_qty != 0):
                # We have remaining qty, button can be shown
                can_recreate = True
                
            order.can_recreate_transfer = can_recreate

    def action_recreate_delivery_wizard(self):
        self.ensure_one()
        
        recreatable_lines = self.order_line.filtered(
            lambda l: (l.product_uom_qty > l.qty_delivered if l.product_uom_qty > 0 else l.product_uom_qty < l.qty_delivered) 
            and l.product_id.type in ['product', 'consu']
        )
        
        if not recreatable_lines:
            raise UserError(_("No remaining quantities to process."))
            
        total_qty = sum(abs(l.product_uom_qty - l.qty_delivered) for l in recreatable_lines)
        line_count = len(recreatable_lines)
        
        warning_msg = False
        active_pickings = self.picking_ids.filtered(lambda p: p.state in ['draft', 'waiting', 'confirmed', 'assigned'])
        if active_pickings:
            warning_msg = _("There are currently active pickings for this order. Recreating may cause duplicate active transfers.")
            
        return {
            'name': _('Recreate Delivery'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.transfer.recreate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_model': 'sale.order',
                'default_order_id': self.id,
                'default_line_count': line_count,
                'default_total_qty': total_qty,
                'default_warning_message': warning_msg,
            }
        }

    def action_recreate_delivery_wizard_batch(self):
        valid_orders = self.filtered(lambda o: o.can_recreate_transfer)
        if not valid_orders:
            raise UserError(_("No selected orders have remaining quantities to process."))
            
        total_qty = sum(
            sum(abs(l.product_uom_qty - l.qty_delivered) for l in o.order_line.filtered(
                lambda l: (l.product_uom_qty > l.qty_delivered if l.product_uom_qty > 0 else l.product_uom_qty < l.qty_delivered) 
                and l.product_id.type in ['product', 'consu']
            )) for o in valid_orders
        )
        line_count = sum(
            len(o.order_line.filtered(
                lambda l: (l.product_uom_qty > l.qty_delivered if l.product_uom_qty > 0 else l.product_uom_qty < l.qty_delivered) 
                and l.product_id.type in ['product', 'consu']
            )) for o in valid_orders
        )
        
        warning_msg = False
        active_pickings = valid_orders.mapped('picking_ids').filtered(lambda p: p.state in ['draft', 'waiting', 'confirmed', 'assigned'])
        if active_pickings:
            warning_msg = _("There are currently active pickings for some orders. Recreating may cause duplicate active transfers.")
            
        return {
            'name': _('Recreate Delivery (Batch)'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.transfer.recreate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_model': 'sale.order',
                'default_order_ids': ','.join(map(str, valid_orders.ids)),
                'default_is_batch': True,
                'default_line_count': line_count,
                'default_total_qty': total_qty,
                'default_warning_message': warning_msg,
            }
        }

    def _recreate_delivery_action(self):
        self.ensure_one()
        _logger.info('=== RECREATE DELIVERY START for %s ===', self.name)

        recreatable_lines = self.order_line.filtered(
            lambda l: (l.product_uom_qty > l.qty_delivered if l.product_uom_qty > 0 else l.product_uom_qty < l.qty_delivered)
            and l.product_id.type in ['product', 'consu']
        )

        _logger.info('All order lines:')
        for line in self.order_line:
            _logger.info('  - Product: %s, type: %s, qty: %s, delivered: %s',
                        line.product_id.display_name, line.product_id.type,
                        line.product_uom_qty, line.qty_delivered)

        _logger.info('Recreatable lines: %s', len(recreatable_lines))
        for line in recreatable_lines:
            _logger.info('  - %s qty=%s delivered=%s', line.product_id.display_name, line.product_uom_qty, line.qty_delivered)

        if not recreatable_lines:
            _logger.warning('No recreatable lines found, returning!')
            return

        # Ensure procurement group exists and is linked to this sale order
        if not self.procurement_group_id:
            group = self.env['procurement.group'].create({
                'name': self.name,
                'move_type': self.picking_policy,
                'sale_id': self.id,
                'partner_id': self.partner_shipping_id.id,
            })
            self.procurement_group_id = group
            _logger.info('Created procurement group %s for %s', group.name, self.name)
        else:
            # Make sure procurement group is linked back to the sale order
            if not self.procurement_group_id.sale_id:
                self.procurement_group_id.sale_id = self.id
                _logger.info('Linked procurement group %s to sale order %s', self.procurement_group_id.name, self.name)

        positive_lines = recreatable_lines.filtered(lambda l: l.product_uom_qty > 0)
        negative_lines = recreatable_lines.filtered(lambda l: l.product_uom_qty < 0)

        created_pickings = self.env['stock.picking']

        if positive_lines:
            picking_type = self.warehouse_id.out_type_id
            if not picking_type:
                raise UserError(_("Cannot find a delivery picking type for the warehouse."))

            location_id = picking_type.default_location_src_id.id
            location_dest_id = (self.partner_shipping_id or self.partner_id).property_stock_customer.id

            picking_vals = {
                'origin': self.name,
                'partner_id': (self.partner_shipping_id or self.partner_id).id,
                'company_id': self.company_id.id,
                'picking_type_id': picking_type.id,
                'location_id': location_id,
                'location_dest_id': location_dest_id,
                'group_id': self.procurement_group_id.id,
                'move_ids': [],
            }

            for line in positive_lines:
                qty_to_process = line.product_uom_qty - line.qty_delivered
                picking_vals['move_ids'].append((0, 0, {
                    'name': line.name or '',
                    'product_id': line.product_id.id,
                    'product_uom_qty': qty_to_process,
                    'product_uom': line.product_uom.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                    'sale_line_id': line.id,
                    'company_id': self.company_id.id,
                    'origin': self.name,
                    'group_id': self.procurement_group_id.id,
                    'picking_type_id': picking_type.id,
                }))

            picking = self.env['stock.picking'].create(picking_vals)
            created_pickings |= picking
            _logger.info('Created POSITIVE picking %s (sale_id=%s) with %d moves', picking.name, picking.sale_id.name, len(picking.move_ids))

        if negative_lines:
            _logger.info('Processing %d NEGATIVE lines', len(negative_lines))
            picking_type = self.warehouse_id.in_type_id
            if not picking_type and self.warehouse_id.out_type_id:
                picking_type = self.warehouse_id.out_type_id.return_picking_type_id
            if not picking_type:
                raise UserError(_("Cannot find a receipt/return picking type for the warehouse."))

            location_id = (self.partner_shipping_id or self.partner_id).property_stock_customer.id
            location_dest_id = picking_type.default_location_dest_id.id

            picking_vals = {
                'origin': self.name,
                'partner_id': (self.partner_shipping_id or self.partner_id).id,
                'company_id': self.company_id.id,
                'picking_type_id': picking_type.id,
                'location_id': location_id,
                'location_dest_id': location_dest_id,
                'group_id': self.procurement_group_id.id,
                'move_ids': [],
            }

            for line in negative_lines:
                qty_to_process = abs(line.product_uom_qty - line.qty_delivered)
                picking_vals['move_ids'].append((0, 0, {
                    'name': line.name or '',
                    'product_id': line.product_id.id,
                    'product_uom_qty': qty_to_process,
                    'product_uom': line.product_uom.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                    'sale_line_id': line.id,
                    'company_id': self.company_id.id,
                    'origin': self.name,
                    'group_id': self.procurement_group_id.id,
                    'picking_type_id': picking_type.id,
                }))

            picking = self.env['stock.picking'].create(picking_vals)
            created_pickings |= picking
            _logger.info('Created NEGATIVE picking %s (sale_id=%s) with %d moves', picking.name, picking.sale_id.name, len(picking.move_ids))

        _logger.info('Total created pickings: %s', created_pickings.mapped('name'))
        for pc in created_pickings:
            pc.action_confirm()
            _logger.info('Confirmed picking %s, state=%s', pc.name, pc.state)
            pc.action_assign()
            _logger.info('Assigned picking %s, state=%s', pc.name, pc.state)

        _logger.info('=== RECREATE DELIVERY END for %s ===', self.name)
        return created_pickings
