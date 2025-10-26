from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    warranty_card_ids = fields.One2many(
        'warranty.card', 
        'sale_order_id', 
        string='Warranty Cards'
    )
    warranty_card_count = fields.Integer(
        string='Warranty Cards Count',
        compute='_compute_warranty_card_count'
    )
    
    def _compute_warranty_card_count(self):
        for order in self:
            order.warranty_card_count = len(order.warranty_card_ids)
    
    def action_create_warranty_card(self):
        """Create warranty cards for delivered products with warranty"""
        self.ensure_one()
        
        # Check if order is delivered
        if self.state not in ['done', 'sale']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Warning',
                    'message': 'Order must be confirmed to create warranty cards',
                    'type': 'warning',
                }
            }
        
        # Get delivered pickings
        delivered_pickings = self.picking_ids.filtered(
            lambda p: p.state == 'done' and p.picking_type_code == 'outgoing'
        )
        
        if not delivered_pickings:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No delivered products found for warranty creation',
                    'type': 'info',
                }
            }
        
        # Create warranty cards
        warranty_cards = self._create_warranty_cards_from_pickings(delivered_pickings)
        
        if warranty_cards:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Created Warranty Cards',
                'res_model': 'warranty.card',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', warranty_cards.ids)],
                'context': {'create': False},
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'No products with warranty configuration found',
                    'type': 'info',
                }
            }
    
    def _create_warranty_cards_from_pickings(self, pickings):
        """Create warranty cards from delivered pickings"""
        WarrantyCard = self.env['warranty.card']
        warranty_cards = WarrantyCard
        
        for picking in pickings:
            for move_line in picking.move_line_ids:
                product = move_line.product_id
                
                # Check if product has warranty configuration
                if (product.product_tmpl_id.warranty_duration <= 0):
                    continue
                
                # Check if warranty card already exists
                existing = WarrantyCard.search([
                    ('sale_order_id', '=', self.id),
                    ('product_id', '=', product.id),
                    ('lot_id', '=', move_line.lot_id.id if move_line.lot_id else False),
                ], limit=1)
                
                if existing:
                    continue
                
                # Create warranty card
                warranty_vals = {
                    'partner_id': self.partner_id.id,
                    'product_id': product.id,
                    'lot_id': move_line.lot_id.id if move_line.lot_id else False,
                    'start_date': picking.date_done.date() if picking.date_done else fields.Date.today(),
                    'sale_order_id': self.id,
                    'picking_id': picking.id,
                    'state': 'active',
                }
                
                warranty_card = WarrantyCard.create(warranty_vals)
                warranty_cards += warranty_card
                
                # Post message on picking
                picking.message_post(
                    body=f'Warranty card {warranty_card.name} created for product {product.display_name}',
                    subject='Warranty Card Created'
                )
        
        return warranty_cards
    
    def action_view_warranty_cards(self):
        """View warranty cards related to this sale order"""
        self.ensure_one()
        action = self.env.ref('buz_warranty_management.action_warranty_card').read()[0]
        action['domain'] = [('sale_order_id', '=', self.id)]
        action['context'] = {
            'default_partner_id': self.partner_id.id,
            'default_sale_order_id': self.id,
        }
        return action