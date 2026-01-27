from odoo import api, fields, models, _, tools
from odoo.exceptions import ValidationError

class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    is_standard_cost_pricelist = fields.Boolean(
        string="Is Standard Cost Pricelist",
        help="This pricelist is used as the source of standard cost for margin calculation."
    )

    @api.constrains('is_standard_cost_pricelist')
    def _check_standard_cost_pricelist_unique(self):
        for record in self:
            if record.is_standard_cost_pricelist:
                existing = self.search([
                    ('is_standard_cost_pricelist', '=', True),
                    ('id', '!=', record.id),
                    ('company_id', '=', record.company_id.id)
                ])
                if existing:
                    raise ValidationError(_("Only one Standard Cost Pricelist per company is allowed."))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_standard_cost_pricelist(self):
        if any(pl.is_standard_cost_pricelist for pl in self):
            raise ValidationError(_("You cannot delete the Standard Cost Pricelist. Uncheck the option first if you really want to delete it."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_standard_cost_pricelist'):
                if not self.env.user.has_group('buz_sale_pricelist_standard_cost.group_pricing_admin'):
                    raise ValidationError(_("Only Pricing Admin can create Standard Cost Pricelists."))
        return super().create(vals_list)

    def write(self, vals):
        # Check permissions
        if 'is_standard_cost_pricelist' in vals or any(r.is_standard_cost_pricelist for r in self):
             if not self.env.user.has_group('buz_sale_pricelist_standard_cost.group_pricing_admin') and not self.env.is_superuser():
                  # Allow system calls (superuser)
                  raise ValidationError(_("Only Pricing Admin can modify Standard Cost Pricelists."))
        return super().write(vals)

    def _compute_price_rule(self, products, quantity, currency=None, uom=None, date=False, **kwargs):
        """ Override to support 'standard_cost_pricelist' base. """
        results = super()._compute_price_rule(products, quantity, currency=currency, uom=uom, date=date, **kwargs)
        
        # Collect rules to check
        rule_ids = set()
        for res in results.values():
            if res[1]:
                rule_ids.add(res[1])
        
        if not rule_ids:
            return results

        rules = self.env['product.pricelist.item'].browse(rule_ids)
        rules_map = {r.id: r for r in rules}

        for product in products:
            price, rule_id = results.get(product.id, (0.0, False))
            if not rule_id:
                continue
            
            rule = rules_map.get(rule_id)
            if rule and rule.compute_price == 'formula' and rule.base == 'standard_cost_pricelist' and rule.base_pricelist_id:
                # Get price from source pricelist with qty=1
                src_pricelist = rule.base_pricelist_id
                
                # Use _get_product_price to resolve the source price
                # Ensure we handle currency conversion if needed, but _get_product_price handles it if pricelists have different currencies.
                # However, if src_pricelist has different currency, _get_product_price returns value in THAT currency.
                # We need it in THIS pricelist's currency.
                
                base_price = src_pricelist._get_product_price(product, 1.0, date=date, uom=uom or product.uom_id)
                
                # Convert currency if necessary
                if src_pricelist.currency_id != self.currency_id:
                     base_price = src_pricelist.currency_id._convert(
                        base_price, self.currency_id, self.env.company, date or fields.Date.today()
                     )

                # Now apply formula
                price_limit = base_price
                price = (base_price - (base_price * (rule.price_discount / 100))) or 0.0
                if rule.price_round:
                     price = tools.float_round(price, precision_rounding=rule.price_round)
                if rule.price_surcharge:
                     price += rule.price_surcharge
                if rule.price_min_margin:
                     price = max(price, price_limit + rule.price_min_margin)
                if rule.price_max_margin:
                     price = min(price, price_limit + rule.price_max_margin)
                
                results[product.id] = (price, rule_id)
        
        return results
