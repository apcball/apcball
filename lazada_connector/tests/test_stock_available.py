from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('post_install', '-at_install')
class TestStockAvailable(TransactionCase):
    def setUp(self):
        super().setUp()
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.company.id)], limit=1)
        self.location = warehouse.lot_stock_id
        self.shop = self.env['lazada.config'].create({
            'name': 'Stock QA', 'app_key': '100', 'app_secret': 'qa',
            'seller_id': '998811', 'lazada_warehouse_id': warehouse.id})
        self.product = self.env['product.product'].create({
            'name': 'Stock QA', 'type': 'product'})
        self.mapping = self.env['lazada.product.mapping'].create({
            'lazada_config_id': self.shop.id, 'product_id': self.product.id,
            'seller_sku': 'STOCK-QA', 'low_stock_threshold': 10})

    def test_live_stock_reservations_and_override(self):
        Quant = self.env['stock.quant']
        Quant._update_available_quantity(self.product, self.location, 11)
        self.env.invalidate_all()
        self.assertEqual(self.mapping.stock_status, 'ok')
        Quant._update_reserved_quantity(self.product, self.location, 1)
        self.env.invalidate_all()
        self.assertEqual(self.mapping.odoo_free_qty, 10)
        self.assertEqual(self.mapping.stock_status, 'low')
        self.mapping.write({'use_stock_override': True, 'stock_override': 999})
        self.assertEqual(self.mapping.stock_status, 'low')
        result = self.env['lazada.product.mapping'].search([
            ('id', '=', self.mapping.id), ('stock_status', '=', 'low')])
        self.assertEqual(result, self.mapping)
        tiles = self.env['lazada.dashboard'].get_dashboard_data(
            shop_ids=[self.shop.id])['tiles']
        self.assertEqual(tiles['low_stock']['value'], 1)
        Quant._update_reserved_quantity(self.product, self.location, 10)
        self.env.invalidate_all()
        self.assertEqual(self.mapping.stock_status, 'out')

    def test_unknown_and_disabled_threshold(self):
        self.mapping.product_id = False
        self.assertEqual(self.mapping.stock_status, 'unknown')
        self.mapping.product_id = self.product
        self.env['stock.quant']._update_available_quantity(self.product, self.location, 1)
        self.env.invalidate_all()
        self.mapping.low_stock_threshold = 0
        self.assertEqual(self.mapping.stock_status, 'ok')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.mapping.low_stock_threshold = -1
