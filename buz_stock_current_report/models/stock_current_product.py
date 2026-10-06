from odoo import api, fields, models, tools
from odoo.osv.expression import AND


class StockCurrentProduct(models.Model):
    """One card per product for the Current Stock View.

    Built on top of ``stock.current.report`` (per product/location). Rows are
    produced per (product, warehouse) plus one aggregate row per product with
    ``warehouse_id IS NULL`` that sums every warehouse. Unless a domain filters
    on ``warehouse_id`` explicitly, only the aggregate rows are returned (see
    ``_where_calc``), so the "All" view shows each product exactly once.
    """
    _name = 'stock.current.product'
    _description = 'Current Stock by Product'
    _auto = False
    _order = 'default_code, id'

    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_template_id = fields.Many2one(
        'product.template', string='Product Template',
        related='product_id.product_tmpl_id', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', readonly=True)
    main_location_id = fields.Many2one(
        'stock.location', string='Main Location', readonly=True,
        help='Location holding the largest on-hand quantity.')
    category_id = fields.Many2one('product.category', string='Category', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', readonly=True)
    quantity = fields.Float('On Hand', readonly=True, digits=(16, 2))
    free_to_use = fields.Float('Free to Use', readonly=True, digits='Product Unit of Measure')
    incoming = fields.Float('Incoming', readonly=True, digits='Product Unit of Measure')
    outgoing = fields.Float('Outgoing', readonly=True, digits='Product Unit of Measure')
    sale_ok = fields.Boolean('Can be Sold', readonly=True)
    price_with_vat = fields.Float('Price incl. VAT', readonly=True, digits=(16, 2))
    name_eng = fields.Char('Name (Eng)', readonly=True)
    default_code = fields.Char('Internal Reference', readonly=True)
    sku = fields.Char('SKU', readonly=True)
    sales_qty_90d = fields.Float('Sold (90 Days)', readonly=True, digits='Product Unit of Measure')
    has_image = fields.Boolean('Has Image', readonly=True)
    state_badge = fields.Selection(
        [('in_stock', 'In Stock'), ('active', 'Active')],
        string='Status', readonly=True)
    product_name = fields.Char(string='Product Name', related='product_id.name', readonly=True)
    product_tag_ids = fields.Many2many(
        'product.tag', string='Tags',
        related='product_id.product_tmpl_id.product_tag_ids', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        measures = """
            SUM(quantity) AS quantity,
            SUM(free_to_use) AS free_to_use,
            SUM(incoming) AS incoming,
            SUM(outgoing) AS outgoing,
            (ARRAY_AGG(location_id ORDER BY quantity DESC, location_id)
                FILTER (WHERE location_id IS NOT NULL))[1] AS main_location_id,
            MAX(category_id) AS category_id,
            MAX(uom_id) AS uom_id,
            BOOL_OR(sale_ok) AS sale_ok,
            MAX(price_with_vat) AS price_with_vat,
            MAX(name_eng) AS name_eng,
            NULLIF(MAX(default_code), '') AS default_code,
            MAX(sku) AS sku,
            MAX(sales_qty_90d) AS sales_qty_90d
        """
        self._cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH agg AS (
                    SELECT product_id, warehouse_id, {measures}
                    FROM stock_current_report
                    WHERE warehouse_id IS NOT NULL
                    GROUP BY product_id, warehouse_id
                    UNION ALL
                    SELECT product_id, NULL::integer AS warehouse_id, {measures}
                    FROM stock_current_report
                    GROUP BY product_id
                )
                SELECT ROW_NUMBER() OVER (ORDER BY product_id, warehouse_id NULLS FIRST) AS id,
                       agg.*,
                       CASE WHEN agg.free_to_use > 0 THEN 'in_stock' ELSE 'active' END AS state_badge,
                       EXISTS (
                           SELECT 1 FROM ir_attachment ia
                           WHERE ia.res_field IN ('image_1920', 'image_variant_1920')
                             AND ((ia.res_model = 'product.product' AND ia.res_id = agg.product_id)
                               OR (ia.res_model = 'product.template' AND ia.res_id = pp.product_tmpl_id))
                       ) AS has_image
                FROM agg
                JOIN product_product pp ON pp.id = agg.product_id
            )
        """)

    @api.model
    def _where_calc(self, domain, active_test=True):
        domain = list(domain or [])
        # Domains that already pin warehouse rows, or fetch records by id
        # (ORM prefetch/read), must not be restricted to the aggregate rows.
        if not any(isinstance(leaf, (list, tuple)) and leaf and leaf[0] in ('warehouse_id', 'id')
                   for leaf in domain):
            domain = AND([domain, [('warehouse_id', '=', False)]])
        return super()._where_calc(domain, active_test=active_test)

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        """Warehouse panel: count distinct products per warehouse."""
        if field_name != 'warehouse_id':
            return super().search_panel_select_range(field_name, **kwargs)
        domain = AND([
            kwargs.get('search_domain', []),
            kwargs.get('category_domain', []),
            kwargs.get('filter_domain', []),
            [('warehouse_id', '!=', False)],
        ])
        groups = self.read_group(domain, ['warehouse_id'], ['warehouse_id'])
        return {
            'parent_field': False,
            'values': [{
                'id': group['warehouse_id'][0],
                'display_name': group['warehouse_id'][1],
                '__count': group['warehouse_id_count'],
            } for group in groups],
        }

    def action_open_product(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'res_id': self.product_template_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
