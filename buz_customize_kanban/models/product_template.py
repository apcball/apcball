from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    price_with_vat = fields.Float(
        string='Price (Inc. VAT)',
        compute='_compute_price_with_vat',
        digits='Product Price'
    )
    
    available_qty = fields.Float(
        string='Available',
        compute='_compute_available_qty',
        digits='Product Unit of Measure'
    )

    @api.depends('list_price')
    def _compute_price_with_vat(self):
        for product in self:
            product.price_with_vat = product.list_price * 1.07
    
    def _compute_available_qty(self):
        """Compute available quantity from selected locations in configuration"""
        # Get selected locations from configuration
        params = self.env['ir.config_parameter'].sudo()
        location_ids_str = params.get_param('buz_customize_kanban.kanban_location_ids', default='')
        
        if location_ids_str:
            location_ids = [int(id) for id in location_ids_str.split(',') if id]
        else:
            location_ids = []
        
        for product in self:
            available_qty = 0.0
            
            if location_ids:
                # Get stock quants for selected locations only
                quants = self.env['stock.quant'].search([
                    ('product_tmpl_id', '=', product.id),
                    ('location_id', 'in', location_ids)
                ])
                
                # Calculate on hand quantity from selected locations
                on_hand = sum(quants.mapped('quantity'))
                
                # Get incoming moves (to selected locations)
                incoming_moves = self.env['stock.move'].search([
                    ('product_tmpl_id', '=', product.id),
                    ('location_dest_id', 'in', location_ids),
                    ('state', 'in', ['assigned', 'confirmed', 'partially_available']),
                ])
                incoming = sum(incoming_moves.mapped('product_uom_qty'))
                
                # Get outgoing moves (from selected locations)
                outgoing_moves = self.env['stock.move'].search([
                    ('product_tmpl_id', '=', product.id),
                    ('location_id', 'in', location_ids),
                    ('state', 'in', ['assigned', 'confirmed', 'partially_available']),
                ])
                outgoing = sum(outgoing_moves.mapped('product_uom_qty'))
                
                # Available = On Hand + Incoming - Outgoing
                available_qty = on_hand + incoming - outgoing
            else:
                # If no locations selected, use default behavior (all locations)
                available_qty = (product.qty_available + product.incoming_qty) - product.outgoing_qty
            
            product.available_qty = available_qty