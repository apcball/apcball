from odoo import models, fields, api, tools, _

class PricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    installation_price = fields.Float(
        string='Installation Price',
        default=0.0,
        help="Price for installation service associated with this product in this pricelist."
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        try:
            to_log = []
            for record in records:
                # Log creation with initial prices
                if record.compute_price == 'fixed' and (record.fixed_price > 0 or record.installation_price > 0):
                     to_log.append({
                         'pricelist_id': record.pricelist_id.id,
                         'product_tmpl_id': record.product_tmpl_id.id,
                         'product_id': record.product_id.id,
                         'old_price': 0.0,
                         'new_price': record.fixed_price,
                         'old_installation_price': 0.0,
                         'new_installation_price': record.installation_price,
                         'origin': 'create'
                     })
            
            if to_log:
                self.env['pricelist.price.history'].create(to_log)
        except Exception:
            # Prevent logging errors from blocking record creation
            pass
            
        return records

    def write(self, vals):
        # Check if relevant fields are changing
        track_fields = ['fixed_price', 'installation_price', 'compute_price']
        if not any(f in vals for f in track_fields):
            return super().write(vals)

        try:
            to_log = []
            for record in self:
                # We only track simple fixed price rules for clarity
                if record.compute_price == 'fixed' or vals.get('compute_price') == 'fixed':
                     old_p = record.fixed_price if record.compute_price == 'fixed' else 0.0
                     old_i = record.installation_price
                     
                     new_p = vals.get('fixed_price', old_p)
                     new_i = vals.get('installation_price', old_i)
                     
                     # Logic: if values changed significantly
                     if abs(old_p - new_p) > 0.001 or abs(old_i - new_i) > 0.001:
                          to_log.append({
                              'pricelist_id': record.pricelist_id.id,
                              'product_tmpl_id': record.product_tmpl_id.id,
                              'product_id': record.product_id.id,
                              'old_price': old_p,
                              'new_price': new_p,
                              'old_installation_price': old_i,
                              'new_installation_price': new_i,
                              'origin': 'update'
                          })
            
            if to_log:
                self.env['pricelist.price.history'].create(to_log)
        except Exception:
            # Prevent logging errors from blocking record updates
            pass
        
        return super().write(vals)


class ProductPricelistInstallation(models.Model):
    _inherit = 'product.pricelist'

    use_installation_price = fields.Boolean(
        string='Use Installation Price',
        default=False,
        help="When checked, pricelist rules (Discount %% or Formula with Standard Cost Pricelist base) "
             "will use the Installation Price from the Standard Cost Pricelist as the base price."
    )

    def _get_installation_price_from_std_cost_pl(self, product, date=False, uom=False):
        """Find the Standard Cost Pricelist for the current company and return
        the installation_price from the matching rule for the given product."""
        std_cost_pl = self.env['product.pricelist'].search([
            ('is_standard_cost_pricelist', '=', True),
            ('company_id', '=', self.env.company.id),
        ], limit=1)

        if not std_cost_pl:
            return 0.0

        # Get the matching rule from the standard cost pricelist
        rule_result = std_cost_pl._get_product_price_rule(
            product, 1.0, date=date, uom=uom or product.uom_id
        )

        install_price = 0.0
        if rule_result[1]:
            src_item = self.env['product.pricelist.item'].browse(rule_result[1])
            install_price = src_item.installation_price or 0.0

        # Convert currency if necessary
        if std_cost_pl.currency_id != self.currency_id:
            install_price = std_cost_pl.currency_id._convert(
                install_price, self.currency_id, self.env.company,
                date or fields.Date.today()
            )

        return install_price

    def _compute_price_rule(self, products, quantity, currency=None, uom=None, date=False, **kwargs):
        """Override: when use_installation_price is True, recalculate prices
        using installation_price from the Standard Cost Pricelist as the base."""
        results = super()._compute_price_rule(products, quantity, currency=currency, uom=uom, date=date, **kwargs)

        # Only process if this pricelist has the flag enabled
        if not self.use_installation_price:
            return results

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
            if not rule:
                continue

            # Get installation_price from the Standard Cost Pricelist
            install_price = self._get_installation_price_from_std_cost_pl(
                product, date=date, uom=uom
            )

            if install_price <= 0:
                continue

            # Handle "Discount %" (percentage) rules
            if rule.compute_price == 'percentage':
                price = install_price * (1.0 - (rule.percent_price / 100.0))
                results[product.id] = (price, rule_id)

            # Handle "Formula" rules with standard_cost_pricelist base
            elif rule.compute_price == 'formula' and rule.base == 'standard_cost_pricelist':
                base_price = install_price
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
