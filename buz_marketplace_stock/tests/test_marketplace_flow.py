# -*- coding: utf-8 -*-

from datetime import datetime

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMarketplaceFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        if not cls.warehouse:
            cls.warehouse = cls.env['stock.warehouse'].create({
                'name': 'MP WH', 'code': 'MPWH',
                'company_id': cls.company.id,
            })
        cls.buffer_loc = cls.env.ref(
            'buz_marketplace_stock.stock_location_marketplace_buf',
            raise_if_not_found=False) or cls.env['stock.location'].create({
                'name': 'Marketplace Buffer',
                'usage': 'internal',
                'location_id': cls.warehouse.lot_stock_id.location_id.id,
            })
        cls.account = cls.env['buz.marketplace.account'].create({
            'name': 'Shopee Test',
            'platform': 'shopee',
            'company_id': cls.company.id,
            'warehouse_id': cls.warehouse.id,
            'buffer_location_id': cls.buffer_loc.id,
            'shopee_partner_id': '12345',
            'shopee_partner_key': 'secret',
            'shopee_shop_id': '99',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'MP Test Product',
            'type': 'product',
            'marketplace_sku': 'MP-SKU-001',
            'list_price': 100.0,
        })
        cls.mp_product = cls.env['buz.marketplace.product'].create({
            'account_id': cls.account.id,
            'marketplace_item_id': '1001',
            'marketplace_variation_id': False,
            'marketplace_name': 'MP Test Product',
            'marketplace_sku': 'MP-SKU-001',
            'marketplace_price': 150.0,
            'marketplace_stock': 50.0,
            'product_id': cls.product.id,
            'initial_stock_qty': 20.0,
        })

    # -- account constraints --

    def test_01_shopee_requires_partner_id(self):
        with self.assertRaises(UserError):
            self.env['buz.marketplace.account'].create({
                'name': 'Bad Shopee',
                'platform': 'shopee',
                'company_id': self.company.id,
            })

    def test_02_lazada_requires_app_key(self):
        with self.assertRaises(UserError):
            self.env['buz.marketplace.account'].create({
                'name': 'Bad Lazada',
                'platform': 'lazada',
                'company_id': self.company.id,
            })

    # -- product uniqueness --

    def test_03_unique_marketplace_product(self):
        with self.assertRaises(Exception):
            self.env['buz.marketplace.product'].create({
                'account_id': self.account.id,
                'marketplace_item_id': '1001',
                'marketplace_variation_id': False,
                'marketplace_name': 'Dup',
            })

    # -- buffer stock compute --

    def _set_stock(self, product, location, qty):
        self.env['stock.quant'].create({
            'product_id': product.id,
            'location_id': location.id,
            'inventory_quantity': qty,
        }).action_apply_inventory()

    def test_04_odoo_buffer_stock_compute(self):
        self.assertEqual(self.mp_product.odoo_buffer_stock, 0.0)
        self._set_stock(self.product, self.buffer_loc, 15.0)
        self.mp_product.invalidate_recordset(fnames=['odoo_buffer_stock'])
        self.assertEqual(self.mp_product.odoo_buffer_stock, 15.0)

    # -- transfer to buffer wizard --

    def test_05_transfer_to_buffer_wizard(self):
        # put stock in main location
        main_loc = self.warehouse.lot_stock_id
        self._set_stock(self.product, main_loc, 30.0)
        wizard = self.env['buz.marketplace.transfer.to.buffer.wizard'].with_context(
            active_id=self.mp_product.id
        ).create({
            'marketplace_product_id': self.mp_product.id,
            'source_location_id': main_loc.id,
            'transfer_qty': 10.0,
        })
        wizard.action_transfer()
        self.env["buz.marketplace.product"].invalidate_recordset(
            fnames=['odoo_buffer_stock'])
        self.assertEqual(self.mp_product.odoo_buffer_stock, 10.0)
        history = self.env['buz.marketplace.stock.history'].search([
            ('account_id', '=', self.account.id),
            ('change_type', '=', 'transfer_to_buffer'),
        ])
        self.assertTrue(history, 'Transfer history not created')
        self.assertEqual(history.new_qty, 10.0)

    # -- SO creation flow --

    def test_06_create_sale_order_from_marketplace_order(self):
        # seed buffer
        self._set_stock(self.product, self.buffer_loc, 20.0)
        order = self.env['buz.marketplace.order'].create({
            'account_id': self.account.id,
            'marketplace_order_id': 'SHP-ORD-001',
            'name': 'SHP-ORD-001',
            'order_status': 'ready_to_ship',
            'order_date': datetime.now(),
            'total_amount': 150.0,
            'buyer_name': 'Test Buyer',
            'buyer_phone': '0812345678',
            'buyer_address': '123 Test St',
            'state': 'imported',
        })
        self.env['buz.marketplace.order.line'].create({
            'order_id': order.id,
            'product_id': self.product.id,
            'marketplace_product_id': self.mp_product.id,
            'quantity': 2.0,
            'price_unit': 150.0,
        })
        order.action_create_sale_order()
        self.assertTrue(order.sale_order_id, 'SO not created')
        self.assertEqual(order.state, 'delivery_validated')
        self.assertEqual(order.sale_order_id.state, 'sale')
        self.assertTrue(order.picking_id, 'Delivery not created')
        self.assertEqual(order.picking_id.state, 'done')
        # buffer stock should be reduced
        self.env["buz.marketplace.product"].invalidate_recordset(
            fnames=['odoo_buffer_stock'])
        self.assertEqual(self.mp_product.odoo_buffer_stock, 18.0)

    def test_07_create_sale_order_twice_raises(self):
        order = self.env['buz.marketplace.order'].create({
            'account_id': self.account.id,
            'marketplace_order_id': 'SHP-ORD-002',
            'name': 'SHP-ORD-002',
            'order_status': 'ready_to_ship',
            'order_date': datetime.now(),
            'total_amount': 150.0,
            'state': 'imported',
        })
        self.env['buz.marketplace.order.line'].create({
            'order_id': order.id,
            'product_id': self.product.id,
            'marketplace_product_id': self.mp_product.id,
            'quantity': 1.0,
            'price_unit': 150.0,
        })
        # seed buffer
        self._set_stock(self.product, self.buffer_loc, 5.0)
        order.action_create_sale_order()
        with self.assertRaises(UserError):
            order.action_create_sale_order()

    def test_08_refill_insufficient_main_stock(self):
        # buffer empty, main empty -> refill wizard swallows per-product errors
        wizard = self.env['buz.marketplace.refill.stock.wizard'].with_context(
            active_ids=self.mp_product.ids
        ).create({
            'marketplace_product_ids': [(6, 0, self.mp_product.ids)],
        })
        result = wizard.action_refill()
        self.assertEqual(result['params']['type'], 'warning')
        self.assertEqual(result['params']['message'], 'Refilled: 0, Errors: 1')

    def test_09_refill_buffer_already_full(self):
        self._set_stock(self.product, self.buffer_loc, 25.0)  # > initial_stock_qty 20
        with self.assertRaises(UserError):
            self.mp_product.action_refill()

    def test_10_partner_auto_create(self):
        order = self.env['buz.marketplace.order'].create({
            'account_id': self.account.id,
            'marketplace_order_id': 'SHP-ORD-003',
            'name': 'SHP-ORD-003',
            'order_status': 'ready_to_ship',
            'order_date': datetime.now(),
            'total_amount': 150.0,
            'buyer_name': 'New Customer XYZ',
            'buyer_phone': '0900000001',
            'buyer_address': 'XYZ addr',
            'state': 'imported',
        })
        self.env['buz.marketplace.order.line'].create({
            'order_id': order.id,
            'product_id': self.product.id,
            'marketplace_product_id': self.mp_product.id,
            'quantity': 1.0,
            'price_unit': 150.0,
        })
        self._set_stock(self.product, self.buffer_loc, 5.0)
        order.action_create_sale_order()
        self.assertTrue(order.buyer_partner_id)
        self.assertEqual(order.buyer_partner_id.phone, '0900000001')

    def test_11_view_actions_return_dict(self):
        act = self.account.action_view_products()
        self.assertEqual(act['res_model'], 'buz.marketplace.product')
        act2 = self.account.action_view_orders()
        self.assertEqual(act2['res_model'], 'buz.marketplace.order')
        act3 = self.mp_product.action_link_product()
        self.assertEqual(act3['res_model'], 'product.product')

    def test_12_stock_history_difference(self):
        hist = self.env['buz.marketplace.stock.history'].create({
            'product_id': self.product.id,
            'account_id': self.account.id,
            'change_type': 'fetch',
            'old_qty': 10.0,
            'new_qty': 15.0,
            'marketplace_qty': 15.0,
        })
        self.assertEqual(hist.difference, 5.0)
