# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    is_retail_installation = fields.Boolean(
        string='Is Retail Installation Cost',
        default=False,
        help='Use retail installation cost pricing'
    )
    is_project_installation = fields.Boolean(
        string='Is Project Installation Cost',
        default=False,
        help='Use project installation cost pricing'
    )

    @api.constrains('is_retail_installation', 'is_project_installation')
    def _check_installation_selection(self):
        for record in self:
            if record.is_retail_installation and record.is_project_installation:
                raise ValidationError(_('Please select only one installation cost type.'))

    @api.onchange('is_retail_installation')
    def _onchange_is_retail_installation(self):
        if self.is_retail_installation:
            self.is_project_installation = False

    @api.onchange('is_project_installation')
    def _onchange_is_project_installation(self):
        if self.is_project_installation:
            self.is_retail_installation = False
