from odoo import models, fields, api

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
