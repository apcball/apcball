# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from odoo import _,api, fields, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    picking_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Location',
        check_company=True,
        domain="[('usage', '=', 'internal'),('apply_in_sale', '=', True),'|', "
               "('company_id', '=', company_id),('company_id', '=', False)]",
    )

    picking_type_id = fields.Many2one(
        comodel_name='stock.picking.type',
        string='Deliver From',
        check_company=True,
        domain="[('code', '=', 'outgoing'),'|', "
               "('company_id', '=', company_id),('company_id', '=', False)]",
    )

    @api.onchange('picking_location_id')
    def _onchange_picking_type(self):
        """
        get picking from source location
        """
        for record in self:
            if record.picking_location_id:
                picking = self.env['stock.picking.type'].search([
                    ('company_id', '=', record.company_id.id),
                    ('default_location_src_id', '=',
                     record.picking_location_id.id),
                    ('code', '=', 'outgoing'),
                ], limit=1)
                if picking:
                    record.picking_type_id = picking
                else:
                    raise ValidationError(_('No Inventory Operation found'
                                            ' with location!'))

    @api.constrains('picking_type_id', 'picking_location_id')
    def _check_picking_type(self):
        """
        restrict save sale order if no picking related to location
        """
        for record in self:
            if not record.picking_type_id and record.picking_location_id:
                picking = self.env['stock.picking.type'].search([
                    ('company_id', '=', record.company_id.id),
                    ('default_location_src_id', '=',
                     record.picking_location_id.id),
                    ('code', '=', 'outgoing'),
                ], limit=1)
                if not picking:
                    raise ValidationError(_('No Inventory Operation found'
                                            ' with location!'))
                else:
                    raise ValidationError(_('Make sure Operation type '
                                            'is choosen!'))
