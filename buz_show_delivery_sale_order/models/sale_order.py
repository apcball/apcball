from odoo import api, fields, models

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    delivery_address_display = fields.Text(
        string='Full Delivery Address',
        compute='_compute_delivery_address_display',
        store=True,
        groups='account.group_delivery_invoice_address',
    )

    @api.depends('partner_shipping_id', 'partner_shipping_id.street', 
                'partner_shipping_id.street2', 'partner_shipping_id.zip',
                'partner_shipping_id.city', 'partner_shipping_id.state_id',
                'partner_shipping_id.country_id')
    def _compute_delivery_address_display(self):
        for order in self:
            if order.partner_shipping_id:
                partner = order.partner_shipping_id
                address_parts = []
                
                if partner.street:
                    address_parts.append(partner.street)
                if partner.street2:
                    address_parts.append(partner.street2)
                if partner.city:
                    address_parts.append(partner.city)
                if partner.state_id:
                    address_parts.append(partner.state_id.name)
                if partner.zip:
                    address_parts.append(partner.zip)
                if partner.country_id:
                    address_parts.append(partner.country_id.name)
                
                order.delivery_address_display = '\n'.join(filter(None, address_parts))
            else:
                order.delivery_address_display = False