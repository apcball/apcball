from odoo import models, api


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super(StockPicking, self).button_validate()
        # Automatic warranty card creation disabled
        # self._create_warranty_cards()
        return res

    def _create_warranty_cards(self):
        WarrantyCard = self.env['warranty.card']
        
        for picking in self:
            if picking.picking_type_code != 'outgoing' or picking.state != 'done':
                continue
            
            sale_order = picking.sale_id
            partner = picking.partner_id
            
            for move_line in picking.move_line_ids:
                product = move_line.product_id
                
                # auto_warranty check removed - warranty creation is now manual
                # if not product.product_tmpl_id.auto_warranty:
                #     continue
                
                if product.product_tmpl_id.warranty_duration <= 0:
                    continue
                
                existing_warranty = WarrantyCard.search([
                    ('picking_id', '=', picking.id),
                    ('product_id', '=', product.id),
                    ('lot_id', '=', move_line.lot_id.id if move_line.lot_id else False),
                ], limit=1)
                
                if existing_warranty:
                    continue
                
                warranty_vals = {
                    'partner_id': partner.id,
                    'product_id': product.id,
                    'lot_id': move_line.lot_id.id if move_line.lot_id else False,
                    'start_date': picking.date_done.date() if picking.date_done else picking.scheduled_date,
                    'sale_order_id': sale_order.id if sale_order else False,
                    'picking_id': picking.id,
                    'state': 'active',
                }
                
                warranty_card = WarrantyCard.create(warranty_vals)
                
                picking.message_post(
                    body=f'Warranty card {warranty_card.name} created for product {product.display_name}',
                    subject='Warranty Card Created'
                )
        
        return True
