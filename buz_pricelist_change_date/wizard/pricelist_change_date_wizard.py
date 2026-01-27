# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class PricelistChangeDateWizard(models.TransientModel):
    """Wizard to change dates for all pricelist items"""
    _name = 'pricelist.change.date.wizard'
    _description = 'Pricelist Change Date Wizard'

    pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Pricelist',
        required=True,
        readonly=True,
    )
    start_date = fields.Date(
        string='Start Date',
        required=True,
        help='Start date for all price rules in this pricelist'
    )
    end_date = fields.Date(
        string='End Date',
        required=True,
        help='End date for all price rules in this pricelist'
    )

    @api.model
    def default_get(self, fields_list):
        """Set default pricelist_id from context"""
        res = super(PricelistChangeDateWizard, self).default_get(fields_list)
        if 'pricelist_id' in fields_list and self.env.context.get('default_pricelist_id'):
            res['pricelist_id'] = self.env.context.get('default_pricelist_id')
        return res

    def action_apply(self):
        """Apply the date changes to all pricelist items"""
        self.ensure_one()
        
        # Validate that end_date is not earlier than start_date
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise UserError('End date cannot be earlier than start date.')
        
        # Get all pricelist items for this pricelist
        pricelist_items = self.env['product.pricelist.item'].search([
            ('pricelist_id', '=', self.pricelist_id.id)
        ])
        
        if not pricelist_items:
            raise UserError('No price rules found for this pricelist.')
        
        # Update all pricelist items with the new dates
        pricelist_items.write({
            'date_start': self.start_date,
            'date_end': self.end_date,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }