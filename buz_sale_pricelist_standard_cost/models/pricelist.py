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

    def _get_non_zero_standard_cost_fallback_rule(self, product, quantity=1.0, date=False):
        """Return the best non-zero template/category/global fixed rule for product."""
        self.ensure_one()
        date = fields.Date.to_date(date or fields.Date.today())
        category_ids = []
        category = product.categ_id
        while category:
            category_ids.append(category.id)
            category = category.parent_id

        domain = [
            ('pricelist_id', '=', self.id),
            ('compute_price', '=', 'fixed'),
            ('fixed_price', '>', 0),
            ('min_quantity', '<=', quantity or 0.0),
            '|', ('date_start', '=', False), ('date_start', '<=', date),
            '|', ('date_end', '=', False), ('date_end', '>=', date),
            '|',
                '&', ('applied_on', '=', '1_product'), ('product_tmpl_id', '=', product.product_tmpl_id.id),
                '|',
                    '&', ('applied_on', '=', '2_product_category'), ('categ_id', 'in', category_ids),
                    ('applied_on', '=', '3_global'),
        ]
        rules = self.env['product.pricelist.item'].search(domain)
        if not rules:
            return self.env['product.pricelist.item']

        category_rank = {category_id: index for index, category_id in enumerate(category_ids)}
        applied_rank = {
            '1_product': 0,
            '2_product_category': 1,
            '3_global': 2,
        }

        def rule_key(rule):
            category_specificity = 0
            if rule.applied_on == '2_product_category' and rule.categ_id:
                category_specificity = category_rank.get(rule.categ_id.id, len(category_ids))
            return (
                applied_rank.get(rule.applied_on, 99),
                -rule.min_quantity,
                category_specificity,
                -rule.id,
            )

        return rules.sorted(rule_key)[:1]

    def _get_non_zero_standard_cost_fallback_price(self, product, quantity=1.0, date=False):
        """Return a provable fallback cost, or 0.0 when no fallback rule exists."""
        fallback_rule = self._get_non_zero_standard_cost_fallback_rule(product, quantity=quantity, date=date)
        return fallback_rule.fixed_price if fallback_rule else 0.0

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
            if (
                self.is_standard_cost_pricelist
                and rule
                and rule.compute_price == 'fixed'
                and rule.applied_on == '0_product_variant'
                and rule.product_id == product
                and tools.float_is_zero(price, precision_rounding=self.currency_id.rounding)
            ):
                fallback_price = self._get_non_zero_standard_cost_fallback_price(
                    product, quantity=quantity, date=date
                )
                if fallback_price > 0:
                    results[product.id] = (fallback_price, rule_id)
                    price = fallback_price

        return results
