from odoo import models, fields, api, _
from odoo.exceptions import UserError

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    can_recreate_transfer = fields.Boolean(
        compute='_compute_can_recreate_transfer',
        string='Can Recreate Transfer'
    )

    @api.depends('picking_ids.state', 'order_line.qty_received', 'order_line.product_qty')
    def _compute_can_recreate_transfer(self):
        for order in self:
            can_recreate = False
            if order.state not in ['purchase', 'done']:
                order.can_recreate_transfer = False
                continue

            all_received = all(
                (line.qty_received >= line.product_qty if line.product_qty > 0 else line.qty_received <= line.product_qty) 
                for line in order.order_line if line.product_qty != 0
            )
            if all_received:
                order.can_recreate_transfer = False
                continue

            if not order.picking_ids:
                can_recreate = True
            elif all(p.state == 'cancel' for p in order.picking_ids):
                can_recreate = True
            elif any((line.qty_received < line.product_qty if line.product_qty > 0 else line.qty_received > line.product_qty) for line in order.order_line if line.product_qty != 0):
                can_recreate = True
                
            order.can_recreate_transfer = can_recreate

    def action_recreate_receipt_wizard(self):
        self.ensure_one()
        
        recreatable_lines = self.order_line.filtered(
            lambda l: (l.product_qty > l.qty_received if l.product_qty > 0 else l.product_qty < l.qty_received) 
            and l.product_id.type in ['product', 'consu']
        )
        
        if not recreatable_lines:
            raise UserError(_("No remaining quantities to process."))
            
        total_qty = sum(abs(l.product_qty - l.qty_received) for l in recreatable_lines)
        line_count = len(recreatable_lines)
        
        warning_msg = False
        active_pickings = self.picking_ids.filtered(lambda p: p.state in ['draft', 'waiting', 'confirmed', 'assigned'])
        if active_pickings:
            warning_msg = _("There are currently active receipts for this order. Recreating may cause duplicate active transfers.")
            
        return {
            'name': _('Recreate Receipt'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.transfer.recreate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_model': 'purchase.order',
                'default_order_id': self.id,
                'default_line_count': line_count,
                'default_total_qty': total_qty,
                'default_warning_message': warning_msg,
            }
        }

    def action_recreate_receipt_wizard_batch(self):
        valid_orders = self.filtered(lambda o: o.can_recreate_transfer)
        if not valid_orders:
            raise UserError(_("No selected orders have remaining quantities to process."))
            
        total_qty = sum(
            sum(abs(l.product_qty - l.qty_received) for l in o.order_line.filtered(
                lambda l: (l.product_qty > l.qty_received if l.product_qty > 0 else l.product_qty < l.qty_received) 
                and l.product_id.type in ['product', 'consu']
            )) for o in valid_orders
        )
        line_count = sum(
            len(o.order_line.filtered(
                lambda l: (l.product_qty > l.qty_received if l.product_qty > 0 else l.product_qty < l.qty_received) 
                and l.product_id.type in ['product', 'consu']
            )) for o in valid_orders
        )
        
        warning_msg = False
        active_pickings = valid_orders.mapped('picking_ids').filtered(lambda p: p.state in ['draft', 'waiting', 'confirmed', 'assigned'])
        if active_pickings:
            warning_msg = _("There are currently active receipts for some orders. Recreating may cause duplicate active transfers.")
            
        return {
            'name': _('Recreate Receipt (Batch)'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.transfer.recreate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_model': 'purchase.order',
                'default_order_ids': ','.join(map(str, valid_orders.ids)),
                'default_is_batch': True,
                'default_line_count': line_count,
                'default_total_qty': total_qty,
                'default_warning_message': warning_msg,
            }
        }

    def _recreate_receipt_action(self):
        self.ensure_one()
        
        recreatable_lines = self.order_line.filtered(
            lambda l: (l.product_qty > l.qty_received if l.product_qty > 0 else l.product_qty < l.qty_received) 
            and l.product_id.type in ['product', 'consu']
        )
        if not recreatable_lines:
            return
            
        positive_lines = recreatable_lines.filtered(lambda l: l.product_qty > 0)
        negative_lines = recreatable_lines.filtered(lambda l: l.product_qty < 0)
        
        created_pickings = self.env['stock.picking']
        
        if positive_lines:
            picking_type = self.picking_type_id
            if not picking_type:
                raise UserError(_("Picking type is required to recreate receipt."))

            location_id = self.partner_id.property_stock_supplier.id
            location_dest_id = self._get_destination_location()

            picking_vals = {
                'origin': self.name,
                'partner_id': self.partner_id.id,
                'company_id': self.company_id.id,
                'picking_type_id': picking_type.id,
                'location_id': location_id,
                'location_dest_id': location_dest_id,
                'group_id': self.group_id.id,
                'purchase_id': self.id,
                'move_ids': [],
            }
            
            for line in positive_lines:
                qty_to_process = line.product_qty - line.qty_received
                picking_vals['move_ids'].append((0, 0, {
                    'name': line.name or '',
                    'product_id': line.product_id.id,
                    'product_uom_qty': qty_to_process,
                    'product_uom': line.product_uom.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                    'purchase_line_id': line.id,
                    'company_id': self.company_id.id,
                    'origin': self.name,
                    'group_id': self.group_id.id,
                    'picking_type_id': picking_type.id,
                    'price_unit': line.price_unit,
                }))

            picking = self.env['stock.picking'].create(picking_vals)
            created_pickings |= picking

        if negative_lines:
            picking_type = self.picking_type_id.return_picking_type_id
            if not picking_type:
                raise UserError(_("Cannot find a return picking type to process negative lines."))

            location_src_id = self._get_destination_location() # From where we received it
            location_dest_id = self.partner_id.property_stock_supplier.id

            picking_vals = {
                'origin': self.name,
                'partner_id': self.partner_id.id,
                'company_id': self.company_id.id,
                'picking_type_id': picking_type.id,
                'location_id': location_src_id,
                'location_dest_id': location_dest_id,
                'group_id': self.group_id.id,
                'purchase_id': self.id,
                'move_ids': [],
            }
            
            for line in negative_lines:
                qty_to_process = abs(line.product_qty - line.qty_received)
                picking_vals['move_ids'].append((0, 0, {
                    'name': line.name or '',
                    'product_id': line.product_id.id,
                    'product_uom_qty': qty_to_process,
                    'product_uom': line.product_uom.id,
                    'location_id': location_src_id,
                    'location_dest_id': location_dest_id,
                    'purchase_line_id': line.id,
                    'company_id': self.company_id.id,
                    'origin': self.name,
                    'group_id': self.group_id.id,
                    'picking_type_id': picking_type.id,
                    'price_unit': line.price_unit,
                }))
                
            picking = self.env['stock.picking'].create(picking_vals)
            created_pickings |= picking
                
        for pc in created_pickings:
            pc.action_confirm()
            pc.action_assign()
            
        return created_pickings
