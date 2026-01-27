from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    base = fields.Selection(
        selection_add=[('standard_cost_pricelist', 'Standard Cost Pricelist')],
        ondelete={'standard_cost_pricelist': 'set default'}
    )
    
    base_pricelist_id = fields.Many2one(
        'product.pricelist',
        string="Standard Cost Pricelist",
        domain=[('is_standard_cost_pricelist', '=', True)],
        help="The pricelist to use as the source of standard cost."
    )

    @api.constrains('base', 'base_pricelist_id')
    def _check_base_pricelist_id(self):
        for record in self:
            if record.base == 'standard_cost_pricelist' and not record.base_pricelist_id:
                raise ValidationError(_("With 'Standard Cost Pricelist' base, you must select a component pricelist."))
            if record.base_pricelist_id and record.base_pricelist_id.id == record.pricelist_id.id:
                 raise ValidationError(_("You cannot reference the same pricelist."))

    @api.onchange('base')
    def _onchange_base_standard_cost(self):
        if self.base != 'standard_cost_pricelist':
            self.base_pricelist_id = False
