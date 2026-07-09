from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestReserveManagerCore(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.product_reserved = cls.env['product.product'].create({
            'name': 'Reserve Test Product A',
            'detailed_type': 'product',
            'taxes_id': [(5, 0, 0)],
            'list_price': 100.0,
        })
        cls.product_unreserved = cls.env['product.product'].create({
            'name': 'Reserve Test Product B',
            'detailed_type': 'product',
            'taxes_id': [(5, 0, 0)],
            'list_price': 200.0,
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Reserve Test Customer'})
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id

        cls.env['stock.quant'].create({
            'product_id': cls.product_reserved.id,
            'location_id': cls.stock_location.id,
            'quantity': 50.0,
        })

        cls.so_reserved = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'partner_invoice_id': cls.partner.id,
            'partner_shipping_id': cls.partner.id,
            'warehouse_id': cls.warehouse.id,
            'order_line': [Command.create({
                'product_id': cls.product_reserved.id,
                'product_uom_qty': 10.0,
                'price_unit': 100.0,
            })],
        })
        cls.so_reserved.action_confirm()
        cls.move_reserved = cls.env['stock.move'].search([
            ('sale_line_id', 'in', cls.so_reserved.order_line.ids),
        ], limit=1)

        cls.so_unreserved = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'partner_invoice_id': cls.partner.id,
            'partner_shipping_id': cls.partner.id,
            'warehouse_id': cls.warehouse.id,
            'order_line': [Command.create({
                'product_id': cls.product_unreserved.id,
                'product_uom_qty': 10.0,
                'price_unit': 200.0,
            })],
        })
        cls.so_unreserved.action_confirm()
        cls.move_unreserved = cls.env['stock.move'].search([
            ('sale_line_id', 'in', cls.so_unreserved.order_line.ids),
        ], limit=1)

        cls.manager = cls.env['buz.reserve.manager'].create({
            'sale_order_ids': [Command.set(cls.so_reserved.ids)],
            'reservation_status': 'all',
        })
        cls.manager.write({'name': 'RM-TEST-001'})

        cls.manager_unreserved = cls.env['buz.reserve.manager'].create({
            'sale_order_ids': [Command.set(cls.so_unreserved.ids)],
            'reservation_status': 'all',
        })
        cls.manager_unreserved.write({'name': 'RM-TEST-002'})

    def test_01_manager_name_get(self):
        self.assertEqual(self.manager.name_get()[0][1], 'RM-TEST-001')

    def test_02_load_lines(self):
        self.manager.action_load_lines()
        self.assertEqual(self.manager.state, 'loaded')
        self.assertEqual(self.manager.line_count, 1)
        line = self.manager.line_ids[0]
        self.assertEqual(line.sale_order_id, self.so_reserved)
        self.assertEqual(line.product_id, self.product_reserved)
        self.assertEqual(line.reserve_state, 'full')
        self.assertEqual(line.reserved_qty, 10.0)

    def test_03_filter_by_status(self):
        mgr = self.env['buz.reserve.manager'].create({
            'sale_order_ids': [Command.set(self.so_unreserved.ids)],
            'reservation_status': 'none',
            'name': 'STATUS-FILTER',
        })
        mgr.action_load_lines()
        self.assertEqual(mgr.line_count, 1)
        self.assertEqual(mgr.line_ids[0].reserve_state, 'none')

    def test_04_reserve_and_unreserve_line(self):
        self.manager_unreserved.action_load_lines()
        line = self.manager_unreserved.line_ids[0]

        self.env['stock.quant'].create({
            'product_id': self.product_unreserved.id,
            'location_id': self.stock_location.id,
            'quantity': 20.0,
        })

        reserve_result = line.action_reserve()
        self.assertEqual(reserve_result, {'type': 'ir.actions.client', 'tag': 'reload'})
        self.manager_unreserved._refresh_loaded_lines()
        self.assertEqual(line.reserve_state, 'full')
        self.assertEqual(line.reserved_qty, 10.0)

        log_model = self.env.registry.models.get('stock.unreserve.log')
        before_logs = self.env['stock.unreserve.log'].search_count([]) if log_model else 0
        unreserve_result = line.action_unreserve()
        self.assertEqual(unreserve_result, {'type': 'ir.actions.client', 'tag': 'reload'})
        self.manager_unreserved._refresh_loaded_lines()
        self.assertEqual(line.reserve_state, 'none')
        self.assertEqual(line.reserved_qty, 0.0)
        if log_model:
            after_logs = self.env['stock.unreserve.log'].search_count([])
            self.assertGreaterEqual(after_logs, before_logs)

    def test_05_bulk_actions(self):
        self.manager.action_load_lines()
        self.manager_unreserved.action_load_lines()
        self.env['stock.quant'].create({
            'product_id': self.product_unreserved.id,
            'location_id': self.stock_location.id,
            'quantity': 20.0,
        })

        reserve_result = self.manager_unreserved.action_reserve_all()
        self.assertEqual(reserve_result, {'type': 'ir.actions.client', 'tag': 'reload'})
        self.manager_unreserved._refresh_loaded_lines()
        self.assertEqual(self.manager_unreserved.line_ids[0].reserve_state, 'full')

        unreserve_result = self.manager_unreserved.action_unreserve_all()
        self.assertEqual(unreserve_result, {'type': 'ir.actions.client', 'tag': 'reload'})
        self.manager_unreserved._refresh_loaded_lines()
        self.assertEqual(self.manager_unreserved.line_ids[0].reserve_state, 'none')

    def test_06_clear_and_reload(self):
        self.manager.action_load_lines()
        self.assertEqual(self.manager.state, 'loaded')
        clear_result = self.manager.action_clear_lines()
        self.assertEqual(clear_result, {'type': 'ir.actions.client', 'tag': 'reload'})
        self.assertEqual(self.manager.state, 'draft')
        self.assertFalse(self.manager.line_ids)
        reload_result = self.manager.action_reload()
        self.assertEqual(reload_result, {'type': 'ir.actions.client', 'tag': 'reload'})
        self.assertEqual(self.manager.state, 'loaded')
        self.assertTrue(self.manager.line_ids)

    def test_07_no_match_raises(self):
        mgr = self.env['buz.reserve.manager'].create({
            'name': 'NO-MATCH',
            'sale_order_ids': [Command.set(self.so_unreserved.ids)],
            'product_ids': [Command.set([self.product_reserved.id])],
            'reservation_status': 'full',
        })
        with self.assertRaises(UserError):
            mgr.action_load_lines()

    def test_08_policy_blocks_future_delivery_unless_forced(self):
        future_date = fields.Datetime.now() + relativedelta(days=30)
        self.move_unreserved.write({'date': future_date})

        mgr = self.env['buz.reserve.manager'].create({
            'name': 'POLICY-BLOCK',
            'sale_order_ids': [Command.set(self.so_unreserved.ids)],
            'reservation_horizon_days': 21,
        })
        mgr.action_load_lines()
        line = mgr.line_ids[0]
        self.assertEqual(line.reserve_policy_state, 'blocked')
        with self.assertRaises(UserError):
            line.action_reserve()

        mgr.force_reservation_override = True
        mgr.action_load_lines()
        line = mgr.line_ids[0]
        self.assertIn(line.reserve_policy_state, ('allowed', 'paid'))

        self.env['stock.quant'].create({
            'product_id': self.product_unreserved.id,
            'location_id': self.stock_location.id,
            'quantity': 20.0,
        })
        reserve_result = line.action_reserve()
        self.assertEqual(reserve_result, {'type': 'ir.actions.client', 'tag': 'reload'})
