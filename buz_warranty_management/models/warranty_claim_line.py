from odoo import models, fields, api


class WarrantyClaimLine(models.Model):
    _name = 'warranty.claim.line'
    _description = 'Warranty Claim Line'
    _order = 'id'

    claim_id = fields.Many2one(
        'warranty.claim',
        string='Claim',
        required=True,
        ondelete='cascade',
        index=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain="[('type', 'in', ['product', 'consu'])]"
    )
    description = fields.Char(string='Description', compute='_compute_description', store=True, readonly=False)
    qty = fields.Float(
        string='Quantity',
        default=1.0,
        required=True
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        related='product_id.uom_id',
        readonly=True
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot/Serial Number',
        domain="[('product_id', '=', product_id)]"
    )
    need_replacement = fields.Boolean(
        string='Need Replacement',
        default=False,
        help='Mark as replacement item for customer'
    )
    is_consumable = fields.Boolean(
        string='Is Consumable',
        compute='_compute_is_consumable',
        store=True,
        help='If true, expense directly'
    )
    unit_cost = fields.Monetary(
        string='Unit Cost',
        currency_field='currency_id',
        help='For internal cost tracking'
    )
    unit_price = fields.Monetary(
        string='Unit Price',
        currency_field='currency_id',
        help='For customer billing (out-of-warranty)'
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='claim_id.currency_id',
        readonly=True
    )
    move_ids = fields.Many2many(
        'stock.move',
        string='Stock Moves',
        readonly=True,
        help='Related stock movements'
    )
    
    @api.depends('product_id', 'product_id.type')
    def _compute_is_consumable(self):
        for line in self:
            line.is_consumable = line.product_id.type == 'consu'
    
    @api.depends('product_id')
    def _compute_description(self):
        for line in self:
            if line.product_id and not line.description:
                line.description = line.product_id.name
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.unit_cost = self.product_id.standard_price
            self.unit_price = self.product_id.list_price
            if not self.description:
                self.description = self.product_id.name
