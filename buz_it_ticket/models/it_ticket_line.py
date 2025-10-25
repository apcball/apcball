# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class ItTicketLine(models.Model):
    _name = 'it.ticket.line'
    _description = 'IT Ticket Line'
    _order = 'id'

    ticket_id = fields.Many2one('it.ticket', 'Ticket', required=True, ondelete='cascade')
    
    name = fields.Char('Description', required=True)
    
    # For Purchase workflow
    product_id = fields.Many2one('product.product', 'Product')
    uom_id = fields.Many2one('uom.uom', 'Unit of Measure')
    quantity = fields.Float('Quantity', default=1.0)
    estimated_cost = fields.Float('Estimated Cost')
    
    # For Access workflow
    access_type = fields.Selection([
        ('email', 'Email Account'),
        ('erp', 'ERP Access'),
        ('vpn', 'VPN Access'),
        ('drive', 'Drive/Storage'),
        ('shared_folder', 'Shared Folder'),
        ('software', 'Software License'),
        ('other', 'Other'),
    ], string='Access Type')
    
    access_payload = fields.Text('Access Details', help='JSON or text details about the access (groups, roles, modules, etc.)')
    
    notes = fields.Text('Notes')
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Update UOM and other fields when product changes"""
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            self.name = self.product_id.name
            if not self.estimated_cost:
                self.estimated_cost = self.product_id.standard_price