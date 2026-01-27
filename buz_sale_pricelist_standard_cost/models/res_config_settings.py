from odoo import api, fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    minimum_margin_percent = fields.Float(
        string="Minimum Margin (%)",
        config_parameter='sale_pricelist_standard_cost.minimum_margin_percent',
        default=0.0
    )
    block_negative_margin = fields.Boolean(
        string="Block Sales Below Standard Cost",
        config_parameter='sale_pricelist_standard_cost.block_negative_margin'
    )
    
    standard_cost_pricelist_id = fields.Many2one(
        'product.pricelist',
        string="Standard Cost Pricelist",
        help="Select the pricelist used as Standard Cost."
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        pricelist = self.env['product.pricelist'].search([
            ('is_standard_cost_pricelist', '=', True),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        res.update(
            standard_cost_pricelist_id=pricelist.id
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        # Handle pricelist standard cost flag
        # Use sudo() to bypass security checks when applying settings
        SudoPricelist = self.env['product.pricelist'].sudo()
        
        current_pl = SudoPricelist.search([
            ('is_standard_cost_pricelist', '=', True),
            ('company_id', '=', self.env.company.id)
        ])
        
        if self.standard_cost_pricelist_id and self.standard_cost_pricelist_id != current_pl:
            # Uncheck old
            if current_pl:
                current_pl.write({'is_standard_cost_pricelist': False})
            # Check new
            # We must browse with sudo to write
            SudoPricelist.browse(self.standard_cost_pricelist_id.id).write({'is_standard_cost_pricelist': True})
