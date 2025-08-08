# Copyright 2024 Ecosoft Co., Ltd (https://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"
    
    # WHT Tax fields using standard Odoo tax fields
    wht_tax_purchase_id = fields.Many2one(
        'account.tax',
        string='Purchase WHT Tax',
        domain=[('type_tax_use', '=', 'purchase'), ('amount', '<', 0)],
        help='Default WHT tax for purchase of this product',
        company_dependent=True,
    )
    
    wht_tax_sale_id = fields.Many2one(
        'account.tax',
        string='Sale WHT Tax', 
        domain=[('type_tax_use', '=', 'sale'), ('amount', '<', 0)],
        help='Default WHT tax for sale of this product',
        company_dependent=True,
    )
    
    # Auto-assignment based on product type
    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        
        for product in products:
            product._auto_assign_wht_tax()
        
        return products
    
    def write(self, vals):
        res = super().write(vals)
        
        # Re-assign WHT tax if product type changed
        if 'type' in vals or 'categ_id' in vals:
            for product in self:
                product._auto_assign_wht_tax()
        
        return res
    
    def _auto_assign_wht_tax(self):
        """Auto-assign WHT tax based on product type and category"""
        self.ensure_one()
        
        # Skip if WHT tax already assigned manually
        if self.wht_tax_purchase_id:
            return
        
        # Get WHT taxes
        service_wht = self.env.ref('l10n_th_account_tax.tax_wht_service_3_purchase', raise_if_not_found=False)
        rental_wht = self.env.ref('l10n_th_account_tax.tax_wht_rental_5_purchase', raise_if_not_found=False)
        professional_wht = self.env.ref('l10n_th_account_tax.tax_wht_professional_5_purchase', raise_if_not_found=False)
        
        # Auto-assign based on product type
        if self.type == 'service':
            # Check category for more specific assignment
            if self.categ_id:
                category_name = self.categ_id.name.lower()
                
                if 'rental' in category_name or 'rent' in category_name:
                    self.wht_tax_purchase_id = rental_wht
                elif 'professional' in category_name or 'consult' in category_name:
                    self.wht_tax_purchase_id = professional_wht
                else:
                    self.wht_tax_purchase_id = service_wht
            else:
                # Default service WHT
                self.wht_tax_purchase_id = service_wht
    
    @api.onchange('type', 'categ_id')
    def _onchange_type_wht_tax(self):
        """Suggest WHT tax when product type or category changes"""
        if not self.wht_tax_purchase_id:
            self._auto_assign_wht_tax()


class ProductCategory(models.Model):
    _inherit = "product.category"
    
    default_wht_tax_purchase_id = fields.Many2one(
        'account.tax',
        string='Default Purchase WHT Tax',
        domain=[('type_tax_use', '=', 'purchase'), ('amount', '<', 0)],
        help='Default WHT tax for products in this category'
    )
    
    default_wht_tax_sale_id = fields.Many2one(
        'account.tax',
        string='Default Sale WHT Tax',
        domain=[('type_tax_use', '=', 'sale'), ('amount', '<', 0)],
        help='Default WHT tax for products in this category'
    )


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"
    
    @api.onchange('product_id')
    def _onchange_product_id_wht_tax(self):
        """Auto-assign WHT tax when product is selected"""
        if self.product_id and self.move_id.move_type in ('in_invoice', 'in_refund'):
            # Purchase invoice - assign WHT tax from product
            if self.product_id.wht_tax_purchase_id:
                # Add WHT tax to existing taxes
                current_taxes = self.tax_ids or self.env['account.tax']
                wht_tax = self.product_id.wht_tax_purchase_id
                
                # Check if WHT tax not already in taxes
                if wht_tax not in current_taxes:
                    self.tax_ids = current_taxes | wht_tax
        
        elif self.product_id and self.move_id.move_type in ('out_invoice', 'out_refund'):
            # Sale invoice - assign WHT tax from product  
            if self.product_id.wht_tax_sale_id:
                current_taxes = self.tax_ids or self.env['account.tax']
                wht_tax = self.product_id.wht_tax_sale_id
                
                if wht_tax not in current_taxes:
                    self.tax_ids = current_taxes | wht_tax
