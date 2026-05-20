from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    kanban_price = fields.Float(
        string='Price',
        compute='_compute_kanban_price',
        digits='Product Price',
    )

    kanban_available_qty = fields.Float(
        string='Available',
        compute='_compute_kanban_available_qty',
        digits='Product Unit of Measure',
    )

    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        compute='_compute_warehouse_id',
        search='_search_warehouse_id',
    )

    @api.depends_context('pricelist')
    def _compute_kanban_price(self):
        params = self.env['ir.config_parameter'].sudo()
        pricelist_id = params.get_param('buz_customize_kanban.kanban_pricelist_id')
        pricelist = self.env['product.pricelist'].browse(int(pricelist_id)) if pricelist_id else False
        for product in self:
            if pricelist and pricelist.exists():
                product.kanban_price = pricelist._get_product_price(product, 1.0)
            else:
                product.kanban_price = product.list_price

    def _compute_kanban_available_qty(self):
        params = self.env['ir.config_parameter'].sudo()
        warehouse_id = params.get_param('buz_customize_kanban.kanban_warehouse_id')
        warehouse = self.env['stock.warehouse'].browse(int(warehouse_id)) if warehouse_id else False
        for product in self:
            if warehouse and warehouse.exists():
                product_with_context = product.with_context(warehouse=warehouse.id)
                product.kanban_available_qty = product_with_context.qty_available
            else:
                product.kanban_available_qty = product.qty_available

    def _compute_warehouse_id(self):
        for product in self:
            product.warehouse_id = False

    def _search_warehouse_id(self, operator, value):
        if not value:
            return []
        if operator in ('=', '!='):
            warehouse_ids = [value]
        elif operator in ('in', 'not in'):
            warehouse_ids = value
        else:
            return []
        warehouses = self.env['stock.warehouse'].browse(warehouse_ids).exists()
        if not warehouses:
            return []
        location_ids = []
        for wh in warehouses:
            child_locs = self.env['stock.location'].search_read(
                [('id', 'child_of', wh.view_location_id.id)],
                ['id'],
            )
            location_ids.extend([loc['id'] for loc in child_locs])
        location_ids = list(set(location_ids))
        if not location_ids:
            return []
        if operator in ('=', 'in'):
            quant_domain = [('location_id', 'in', location_ids), ('quantity', '>', 0)]
        else:
            all_wh = self.env['stock.warehouse'].search([]).mapped('view_location_id').ids
            all_wh_children = self.env['stock.location'].search([('id', 'child_of', all_wh)]).ids
            other_locs = list(set(all_wh_children) - set(location_ids))
            if other_locs:
                quant_domain = [('location_id', 'in', other_locs), ('quantity', '>', 0)]
            else:
                return [('id', '=', 0)]
        quants = self.env['stock.quant'].search_read(quant_domain, ['product_id'])
        product_ids = list(set(q['product_id'][0] for q in quants))
        if not product_ids:
            return [('id', '=', 0)]
        products = self.env['product.product'].browse(product_ids)
        template_ids = products.mapped('product_tmpl_id').ids
        return [('id', 'in', template_ids)]
