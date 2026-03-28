from odoo import models, fields, api, _
from odoo.exceptions import UserError

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

    def _recreate_delivery_action(self):
        self.ensure_one()
        
        recreatable_lines = self.order_line.filtered(
            lambda l: (l.product_uom_qty > l.qty_delivered if l.product_uom_qty > 0 else l.product_uom_qty < l.qty_delivered) 
            and l.product_id.type in ['product', 'consu']
        )
        if not recreatable_lines:
            return
            
        positive_lines = recreatable_lines.filtered(lambda l: l.product_uom_qty > 0)
        negative_lines = recreatable_lines.filtered(lambda l: l.product_uom_qty < 0)
        
        created_pickings = self.env['stock.picking']
        
        if positive_lines:
            picking_type = self.warehouse_id.out_type_id
            if not picking_type:
                raise UserError(_("Cannot find a delivery picking type for the warehouse."))
                
            picking_vals = {
                'origin': self.name,
                'partner_id': self.partner_shipping_id.id or self.partner_id.id,
                'company_id': self.company_id.id,
                'picking_type_id': picking_type.id,
                'location_id': picking_type.default_location_src_id.id,
                'location_dest_id': self.partner_shipping_id.property_stock_customer.id,
                'group_id': self.procurement_group_id.id,
                'sale_id': self.id,
            }
            picking = self.env['stock.picking'].create(picking_vals)
            created_pickings |= picking
            
            for line in positive_lines:
                qty_to_process = line.product_uom_qty - line.qty_delivered
                move_vals = {
                    'name': line.name or '',
                    'product_id': line.product_id.id,
                    'product_uom_qty': qty_to_process,
                    'product_uom': line.product_uom.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'sale_line_id': line.id,
                    'company_id': self.company_id.id,
                    'origin': self.name,
                    'group_id': self.procurement_group_id.id,
                    'picking_type_id': picking_type.id,
                }
                self.env['stock.move'].create(move_vals)
                
        if negative_lines:
            picking_type = self.warehouse_id.in_type_id
            if not picking_type and self.warehouse_id.out_type_id:
                picking_type = self.warehouse_id.out_type_id.return_type_id
            if not picking_type:
                raise UserError(_("Cannot find a receipt/return picking type for the warehouse."))
                
            picking_vals = {
                'origin': self.name,
                'partner_id': self.partner_shipping_id.id or self.partner_id.id,
                'company_id': self.company_id.id,
                'picking_type_id': picking_type.id,
                'location_id': self.partner_shipping_id.property_stock_customer.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
                'group_id': self.procurement_group_id.id,
                'sale_id': self.id,
            }
            picking = self.env['stock.picking'].create(picking_vals)
            created_pickings |= picking
            
            for line in negative_lines:
                qty_to_process = abs(line.product_uom_qty - line.qty_delivered)
                move_vals = {
                    'name': line.name or '',
                    'product_id': line.product_id.id,
                    'product_uom_qty': qty_to_process,
                    'product_uom': line.product_uom.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'sale_line_id': line.id,
                    'company_id': self.company_id.id,
                    'origin': self.name,
                    'group_id': self.procurement_group_id.id,
                    'picking_type_id': picking_type.id,
                }
                self.env['stock.move'].create(move_vals)
                
        for pc in created_pickings:
            pc.action_confirm()
            pc.action_assign()
            
        return created_pickings
