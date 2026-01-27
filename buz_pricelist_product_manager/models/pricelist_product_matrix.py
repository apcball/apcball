from odoo import models, fields, api, tools, _
from odoo.exceptions import UserError

class PricelistProductMatrix(models.Model):
    _name = 'pricelist.product.matrix'
    _description = 'Pricelist Product Matrix'
    _auto = False
    _order = 'pricelist_id, product_tmpl_id, min_quantity'

    id = fields.Integer(string="ID")
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', required=True, readonly=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', readonly=True)
    product_variant_id = fields.Many2one('product.product', string='Product Variant', readonly=True)
    category_id = fields.Many2one('product.category', string='Category', readonly=True)
    
    base_price = fields.Float(string='Sales Price', readonly=True)
    
    rule_id = fields.Many2one('product.pricelist.item', string='Pricelist Rule', readonly=True)
    rule_type = fields.Selection([
        ('fixed', 'Fixed Price'),
        ('percentage', 'Percentage (discount)'),
        ('formula', 'Formula')
    ], string='Rule Type')
    
    price = fields.Float(string='Fixed Price')
    percent_price = fields.Float(string='Percentage')
    installation_price = fields.Float(string='Installation Price')
    
    min_quantity = fields.Float(string='Min. Qty', digits='Product Unit of Measure')
    date_start = fields.Datetime(string='Start Date')
    date_end = fields.Datetime(string='End Date')
    
    computed_price = fields.Float(string='Final Price', compute='_compute_price')
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        
        # Check if column exists to avoid errors during upgrade/install
        self.env.cr.execute("""
            SELECT count(*) 
            FROM information_schema.columns 
            WHERE table_name = 'product_pricelist_item' 
            AND column_name = 'installation_price'
        """)
        has_install_price = self.env.cr.fetchone()[0] > 0
        
        install_price_expr = "COALESCE(item_v.installation_price, item_t.installation_price)" if has_install_price else "0.0"

        # Optimization: Use stable, non-colliding IDs.
        # Strategy:
        # 1. If Rule Exists: Use the Rule ID (product_pricelist_item.id). This matches Odoo's native ID usage.
        # 2. If No Rule (Empty Slot): Use a Synthetic ID.
        #    Base: 3,000,000,000,000 (3 Trillion) to avoid collision with real IDs (int4/int8 sequence).
        #    Formula: Base + (PricelistID * 100,000,000) + ProductID.
        #    Capacity: Supports 100M Products per Pricelist.
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    CASE 
                        WHEN COALESCE(item_v.id, item_t.id) IS NOT NULL THEN COALESCE(item_v.id, item_t.id)::bigint
                        ELSE (3000000000000 + pl.id::bigint * 100000000 + pp.id::bigint)::bigint
                    END AS id,
                    pl.id AS pricelist_id,
                    pl.currency_id AS currency_id,
                    pp.id AS product_variant_id,
                    pp.product_tmpl_id AS product_tmpl_id,
                    pt.categ_id AS category_id,
                    pt.list_price AS base_price,
                    COALESCE(item_v.id, item_t.id) AS rule_id,
                    COALESCE(item_v.compute_price, item_t.compute_price) AS rule_type,
                    COALESCE(item_v.fixed_price, item_t.fixed_price) AS price,
                    COALESCE(item_v.percent_price, item_t.percent_price) AS percent_price,
                    %s AS installation_price,
                    COALESCE(item_v.min_quantity, item_t.min_quantity) AS min_quantity,
                    COALESCE(item_v.date_start, item_t.date_start) AS date_start,
                    COALESCE(item_v.date_end, item_t.date_end) AS date_end
                FROM
                    product_product pp
                    JOIN product_template pt ON pp.product_tmpl_id = pt.id
                    CROSS JOIN product_pricelist pl
                    LEFT JOIN product_pricelist_item item_v ON (
                        item_v.pricelist_id = pl.id
                        AND item_v.product_id = pp.id
                    )
                    LEFT JOIN product_pricelist_item item_t ON (
                        item_t.pricelist_id = pl.id
                        AND item_t.product_tmpl_id = pt.id
                        AND item_t.product_id IS NULL
                    )
                WHERE
                     pp.active = TRUE AND pt.active = TRUE
            )
        """ % (self._table, install_price_expr))

    @api.depends_context('pricelist', 'quantity', 'date')
    def _compute_price(self):
        # Optimization: Group by (pricelist, min_quantity, date) to batch calls
        grouped = {}
        for record in self:
            if not record.pricelist_id or not record.product_variant_id:
                record.computed_price = 0.0
                continue
                
            # Key for batching
            key = (
                record.pricelist_id,
                record.min_quantity or 1.0,
                record.date_start or fields.Datetime.now()
            )
            if key not in grouped:
                grouped[key] = self.env['pricelist.product.matrix']
            grouped[key] += record
            
        # Process batches
        for (pricelist, qty, date), records in grouped.items():
            products = records.mapped('product_variant_id')
            # _compute_price_rule returns {product_id: (price, rule_id)}
            prices = pricelist._compute_price_rule(products, quantity=qty, date=date)
            
            for record in records:
                price_info = prices.get(record.product_variant_id.id)
                record.computed_price = price_info[0] if price_info else 0.0

    def write(self, vals):
        # Handling Inline Edit
        # Allowed fields to edit: rule_type, price, percent_price, min_quantity, date_start, date_end, installation_price
        editable_fields = ['rule_type', 'price', 'percent_price', 'min_quantity', 'date_start', 'date_end', 'installation_price']
        
        changes = {k: v for k, v in vals.items() if k in editable_fields}
        if not changes:
            return True

        # Map 'price' back to 'fixed_price'
        if 'price' in changes:
            changes['fixed_price'] = changes.pop('price')
            
        # Group records
        records_with_rules = self.filtered('rule_id')
        records_without_rules = self - records_with_rules
        
        # 1. Update Existing Rules
        if records_with_rules:
            # Batch update
            # Optimization: skip owner check for speed, assume view constraints
            records_with_rules.mapped('rule_id').write(changes)
            
        # 2. Create New Rules
        if records_without_rules:
            to_create = []
            for record in records_without_rules:
                # Determine rule type: from changes, or view column, or default 'fixed'
                new_rule_type = changes.get('rule_type') or record.rule_type or 'fixed'
                
                new_rule_vals = {
                    'pricelist_id': record.pricelist_id.id,
                    'product_id': record.product_variant_id.id,
                    'applied_on': '0_product_variant',
                    'compute_price': new_rule_type,
                }
                new_rule_vals.update(changes)
                to_create.append(new_rule_vals)
            
            if to_create:
                self.env['product.pricelist.item'].create(to_create)
        
        return True
