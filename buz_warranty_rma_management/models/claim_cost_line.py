# Part of buz_warranty_rma_management Odoo module.
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class BuzClaimCostLine(models.Model):
    _name = 'buz.claim.cost.line'
    _description = 'Warranty Claim Cost Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    claim_id = fields.Many2one(
        'buz.warranty.claim',
        string='Warranty Claim',
        required=True,
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product/Service',
        required=True
    )
    name = fields.Char(
        string='Description',
        required=True
    )
    quantity = fields.Float(
        string='Quantity',
        default=1.0,
        required=True
    )
    price_unit = fields.Float(
        string='Unit Price',
        required=True
    )
    tax_ids = fields.Many2many(
        'account.tax',
        string='Taxes'
    )
    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='claim_id.partner_id.property_product_pricelist.currency_id',
        store=True
    )

    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit