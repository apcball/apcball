# Part of buz_warranty_rma_management Odoo module.
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class BuzWarrantyTemplate(models.Model):
    _name = 'buz.warranty.template'
    _description = 'Warranty Template'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Template Name',
        required=True,
        translate=True
    )
    code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        unique=True
    )
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product Template',
        required=True
    )
    coverage_type = fields.Selection([
        ('free', 'Free Warranty'),
        ('extended', 'Extended Warranty')
    ], string='Coverage Type', required=True, default='free')
    
    duration_months = fields.Integer(
        string='Duration (Months)',
        required=True,
        default=12
    )
    terms = fields.Text(
        string='Terms and Conditions',
        translate=True
    )
    sell_product_id = fields.Many2one(
        'product.product',
        string='Sellable Product for Extended Warranty',
        help="Product to be sold when creating extended warranty invoices"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    # Smart button: number of contracts created from this template
    contract_count = fields.Integer(
        string='Contract Count',
        compute='_compute_contract_count',
        store=True
    )

    @api.constrains('duration_months')
    def _check_duration_months(self):
        for record in self:
            if record.duration_months <= 0:
                raise ValidationError(_("Duration in months must be greater than 0"))

    @api.constrains('code')
    def _check_unique_code(self):
        for record in self:
            templates = self.search([('code', '=', record.code), ('id', '!=', record.id)])
            if templates:
                raise ValidationError(_("Code must be unique"))

    @api.depends('name')
    def _compute_contract_count(self):
        for template in self:
            template.contract_count = self.env['buz.warranty.contract'].search_count([
                ('template_id', '=', template.id)
            ])

    def action_view_contracts(self):
        """Action to view contracts created from this template"""
        action = self.env["ir.actions.actions"]._for_xml_id(
            "buz_warranty_rma_management.action_warranty_contract_list"
        )
        action['domain'] = [('template_id', '=', self.id)]
        return action