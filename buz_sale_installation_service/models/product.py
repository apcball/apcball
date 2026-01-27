# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    installation_fee = fields.Monetary(
        string='Installation Fee',
        currency_field='currency_id',
        help='Installation fee for this product. Will be added as separate service line in sale order.'
    )
    
    installation_service_product_id = fields.Many2one(
        'product.product',
        string='Installation Service Product',
        domain="[('type', '=', 'service')]",
        help='Service product used for installation fee. If not set, company default will be used.'
    )

    def _get_default_installation_service_product(self):
        """Get default installation service product from company or create one"""
        company = self.env.company
        if company.default_installation_service_product_id:
            return company.default_installation_service_product_id
        
        # Try to get the default product from data
        default_product = self.env.ref('buz_sale_installation_service.product_installation_service', raise_if_not_found=False)
        if default_product:
            # Auto-set as company default
            company.default_installation_service_product_id = default_product.id
            return default_product
        
        return False

    @api.onchange('installation_fee')
    def _onchange_installation_fee(self):
        """When installation fee is set, ensure installation service product is configured"""
        if self.installation_fee > 0 and not self.installation_service_product_id:
            self.installation_service_product_id = self._get_default_installation_service_product()


class ProductProduct(models.Model):
    _inherit = 'product.product'

    installation_fee = fields.Monetary(
        related='product_tmpl_id.installation_fee',
        readonly=False,
        store=True
    )
    
    installation_service_product_id = fields.Many2one(
        related='product_tmpl_id.installation_service_product_id',
        readonly=False,
        store=True
    )
