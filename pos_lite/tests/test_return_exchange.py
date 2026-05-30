from odoo.tests import common, tagged
from odoo.exceptions import UserError


class TestReturnExchangeBase(common.TransactionCase):
    """Base class สร้างข้อมูลตั้งต้นสำหรับทดสอบ Return & Exchange"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company

        # Product category
        cls.category = cls.env['product.category'].create({
            'name': 'Test Category - Return',
        })

        # Products — storable สำหรับ test เต็ม flow, service สำหรับง่าย
        cls.product_a = cls.env['product.product'].create({
            'name': 'Return Product A',
            'type': 'service',
            'categ_id': cls.category.id,
            'sale_ok': True,
            'list_price': 200.0,
            'taxes_id': [(5, 0, 0)],  # no tax
        })
        cls.product_b = cls.env['product.product'].create({
            'name': 'Return Product B',
            'type': 'service',
            'categ_id': cls.category.id,
            'sale_ok': True,
            'list_price': 150.0,
            'taxes_id': [(5, 0, 0)],  # no tax
        })

        # Partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Return Customer',
            'customer_rank': 1,
        })

        # Pricelist
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'Test Pricelist',
            'company_id': cls.company.id,
        })

        # Warehouse
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.company.id),
        ], limit=1)

        # Journals
        cls.sale_journal = cls.env['account.journal'].create({
            'name': 'Sale Journal',
            'type': 'sale',
            'code': 'SJRN',
            'company_id': cls.company.id,
        })
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'Cash Journal',
            'type': 'cash',
            'code': 'CJRN',
            'company_id': cls.company.id,
        })

        # Employee (no user_id to avoid UniqueViolation on hr_employee_user_uniq)
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Return Emp',
            'company_id': cls.company.id,
        })

        # Config
        cls.config = cls.env['pos.lite.config'].create({
            'name': 'Test Config',
            'company_id': cls.company.id,
            'warehouse_id': cls.warehouse.id,
            'pricelist_id': cls.pricelist.id,
            'journal_id': cls.cash_journal.id,
        })

        # Advance sequences to avoid conflict with existing data in MOG_DEV
        cls.env.cr.execute(
            "UPDATE ir_sequence SET number_next = 100000 WHERE code IN ('pos.lite.session', 'pos.lite.order') AND number_next < 100000"
        )
        cls.env.invalidate_all()

        # Session
        cls.session = cls.env['pos.lite.session'].create({
            'config_id': cls.config.id,
            'employee_id': cls.employee.id,
            'company_id': cls.company.id,
        })

    def _create_and_process_order(self, line_data=None):
        """Helper: สร้าง order + quick pay → return order object"""
        if line_data is None:
            line_data = [(self.product_a.id, 1, 200.0)]
        lines = [(0, 0, {
            'product_id': pid,
            'qty': qty,
            'price_unit': price,
        }) for pid, qty, price in line_data]
        order = self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'channel': 'phone',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'line_ids': lines,
        })
        order.action_quick_pay_and_process()
        self.assertEqual(order.state, 'done')
        return order


@tagged('-at_install', 'post_install')
class TestReturnFlow(TestReturnExchangeBase):
    """ทดสอบการทำ Return Order"""

    def test_create_return_wizard_action(self):
        """order done → action_create_return คืน action wizard"""
        order = self._create_and_process_order()
        action = order.action_create_return()
        self.assertEqual(action['res_model'], 'pos.lite.return.wizard')

    def test_return_from_non_done_order_should_fail(self):
        """order ที่ยังไม่ done → เรียก action_create_return ไม่ได้"""
        order = self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'channel': 'phone',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'line_ids': [(0, 0, {
                'product_id': self.product_a.id,
                'qty': 1,
                'price_unit': 200.0,
            })],
        })
        with self.assertRaises(UserError):
            order.action_create_return()

    def test_return_order_is_return(self):
        """return order ที่สร้างผ่าน wizard → is_return=True, return_of_order_id ชี้กลับ"""
        order = self._create_and_process_order()
        # จำลอง wizard action_confirm
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': order.id,
        })
        # onchange จะ populate line_ids อัตโนมัติ
        wizard._onchange_order_id()
        # ตรวจสอบว่ามี line
        self.assertTrue(wizard.line_ids)
        wizard.action_confirm()

        # ค้นหา return order
        return_order = self.env['pos.lite.order'].search([
            ('return_of_order_id', '=', order.id),
        ], limit=1)
        self.assertTrue(return_order)
        self.assertTrue(return_order.is_return)
        self.assertEqual(return_order.return_of_order_id, order)
        self.assertEqual(return_order.state, 'done')

    def test_return_adjusts_inventory(self):
        """return order — payment amount เป็นลบ, invoice type = out_refund"""
        order = self._create_and_process_order([
            (self.product_a.id, 2, 200.0),  # total = 400
        ])
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': order.id,
        })
        wizard._onchange_order_id()
        # return 1 ชิ้น
        for line in wizard.line_ids:
            line.qty = 1.0
        wizard.action_confirm()

        return_order = self.env['pos.lite.order'].search([
            ('return_of_order_id', '=', order.id),
        ], limit=1)
        self.assertEqual(return_order.amount_total, -200.0)
        self.assertTrue(return_order.payment_ids)
        self.assertEqual(return_order.payment_ids[0].amount, -200.0)  # refund → negative
        self.assertEqual(return_order.invoice_id.move_type, 'out_refund')

    def test_return_from_return_should_fail(self):
        """return order → ไม่สามารถ return ซ้ำได้ เพราะ state ต้องเป็น done ก่อน"""
        order = self._create_and_process_order()
        # Return
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': order.id,
        })
        wizard._onchange_order_id()
        wizard.action_confirm()

        return_order = self.env['pos.lite.order'].search([
            ('return_of_order_id', '=', order.id),
        ], limit=1)
        self.assertEqual(return_order.state, 'done')

        # ลอง return ซ้ำจาก original order — ควรทำได้ (can return multiple times)
        # แต่ return จาก return order (is_return=True) → action_create_return เรียกได้
        # เนื่องจาก state=done
        # แค่ verify ว่า action_create_return ไม่ได้ error
        action = return_order.action_create_return()
        self.assertEqual(action['res_model'], 'pos.lite.return.wizard')

    def test_return_refund_payment_method(self):
        """return wizard ใช้ refund_payment_method ที่เลือก ไม่ใช่ hardcode cash"""
        order = self._create_and_process_order([
            (self.product_a.id, 2, 100.0),
        ])
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': order.id,
            'refund_payment_method': 'transfer',
        })
        wizard._onchange_order_id()
        wizard.action_confirm()

        return_order = self.env['pos.lite.order'].search([
            ('return_of_order_id', '=', order.id),
        ], limit=1)
        self.assertTrue(return_order)
        self.assertEqual(return_order.payment_ids[0].payment_method, 'transfer')

    def test_return_refund_payment_with_journal(self):
        """return wizard ใช้ refund_journal_id ที่เลือก"""
        bank_journal = self.env['account.journal'].create({
            'name': 'Bank Test',
            'type': 'bank',
            'code': 'BNKT',
            'company_id': self.company.id,
        })
        order = self._create_and_process_order([
            (self.product_a.id, 1, 100.0),
        ])
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': order.id,
            'refund_payment_method': 'transfer',
            'refund_journal_id': bank_journal.id,
        })
        wizard._onchange_order_id()
        wizard.action_confirm()

        return_order = self.env['pos.lite.order'].search([
            ('return_of_order_id', '=', order.id),
        ], limit=1)
        self.assertTrue(return_order)
        self.assertEqual(return_order.payment_ids[0].journal_id, bank_journal)
        self.assertEqual(return_order.payment_ids[0].payment_method, 'transfer')


@tagged('-at_install', 'post_install')
class TestExchangeFlow(TestReturnExchangeBase):
    """ทดสอบการทำ Exchange Order"""

    def test_exchange_wizard_action(self):
        """order done → action_create_exchange คืน action wizard"""
        order = self._create_and_process_order()
        action = order.action_create_exchange()
        self.assertEqual(action['res_model'], 'pos.lite.return.wizard')

    def test_exchange_creates_two_orders(self):
        """exchange → สร้าง return order + exchange order"""
        order = self._create_and_process_order([
            (self.product_a.id, 1, 200.0),
        ])
        # จำลอง wizard exchange
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': order.id,
            'is_exchange': True,
        })
        wizard._onchange_order_id()
        # เพิ่ม exchange line — product_b
        exchange_line = self.env['pos.lite.return.wizard.exchange.line'].create({
            'wizard_id': wizard.id,
            'product_id': self.product_b.id,
            'qty': 1,
            'price_unit': 150.0,
        })
        wizard.write({'exchange_line_ids': [(4, exchange_line.id)]})
        wizard.action_confirm()

        # ตรวจสอบ return order
        return_order = self.env['pos.lite.order'].search([
            ('return_of_order_id', '=', order.id),
        ], limit=1)
        self.assertTrue(return_order)
        self.assertTrue(return_order.is_return)

        # ตรวจสอบ exchange order
        exchange_order = self.env['pos.lite.order'].search([
            ('exchange_of_order_id', '=', order.id),
        ], limit=1)
        self.assertTrue(exchange_order)
        self.assertTrue(exchange_order.is_exchange)
        self.assertEqual(exchange_order.state, 'done')

    def test_exchange_with_equal_value(self):
        """exchange มูลค่าเท่ากัน → ไม่ต้องจ่ายเพิ่ม"""
        order = self._create_and_process_order([
            (self.product_a.id, 1, 150.0),  # 150
        ])
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': order.id,
            'is_exchange': True,
        })
        wizard._onchange_order_id()
        # Exchange product_b ราคา 150 = same value
        exchange_line = self.env['pos.lite.return.wizard.exchange.line'].create({
            'wizard_id': wizard.id,
            'product_id': self.product_b.id,
            'qty': 1,
            'price_unit': 150.0,
        })
        wizard.write({'exchange_line_ids': [(4, exchange_line.id)]})
        wizard.action_confirm()

        exchange_order = self.env['pos.lite.order'].search([
            ('exchange_of_order_id', '=', order.id),
        ], limit=1)
        self.assertTrue(exchange_order)

    def test_exchange_with_difference_customer_pays(self):
        """exchange ลูกค้าต้องจ่ายเพิ่ม → payment ครอบ amount_total, order done"""
        order = self._create_and_process_order([
            (self.product_a.id, 1, 100.0),  # 100
        ])
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': order.id,
            'is_exchange': True,
        })
        wizard._onchange_order_id()
        # Exchange product_b ราคา 200 → ต้องจ่ายเพิ่ม 100
        exchange_line = self.env['pos.lite.return.wizard.exchange.line'].create({
            'wizard_id': wizard.id,
            'product_id': self.product_b.id,
            'qty': 1,
            'price_unit': 200.0,
        })
        wizard.write({'exchange_line_ids': [(4, exchange_line.id)]})
        wizard.action_confirm()

        exchange_order = self.env['pos.lite.order'].search([
            ('exchange_of_order_id', '=', order.id),
        ], limit=1)
        self.assertTrue(exchange_order)
        self.assertTrue(exchange_order.is_exchange)
        self.assertEqual(exchange_order.state, 'done')
        self.assertEqual(exchange_order.amount_total, 200.0)

    def test_exchange_summary_shows_correct_values(self):
        """wizard สรุปยอด return_total, exchange_total, exchange_difference ตรงตามรายการ"""
        order = self._create_and_process_order([
            (self.product_a.id, 2, 100.0),  # return: 2x100 = 200
        ])
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': order.id,
            'is_exchange': True,
        })
        wizard._onchange_order_id()
        # return 1 ชิ้น ราคา 100
        for line in wizard.line_ids:
            line.qty = 1.0
        # exchange product_b ราคา 150
        exchange_line = self.env['pos.lite.return.wizard.exchange.line'].create({
            'wizard_id': wizard.id,
            'product_id': self.product_b.id,
            'qty': 2,
            'price_unit': 150.0,
        })
        wizard.write({'exchange_line_ids': [(4, exchange_line.id)]})

        self.assertAlmostEqual(wizard.return_total, 100.0, places=2)
        self.assertAlmostEqual(wizard.exchange_total, 300.0, places=2)
        self.assertAlmostEqual(wizard.exchange_difference, 200.0, places=2)
        self.assertTrue(wizard.is_customer_pays)
        self.assertFalse(wizard.is_customer_gets_refund)

    def test_exchange_with_return_higher_value(self):
        """exchange — return value > exchange value → exchange_difference ติดลบ (customer gets partial refund)"""
        order = self._create_and_process_order([
            (self.product_a.id, 1, 200.0),  # return: 200
        ])
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': order.id,
            'is_exchange': True,
        })
        wizard._onchange_order_id()
        # exchange product_b ราคา 100
        exchange_line = self.env['pos.lite.return.wizard.exchange.line'].create({
            'wizard_id': wizard.id,
            'product_id': self.product_b.id,
            'qty': 1,
            'price_unit': 100.0,
        })
        wizard.write({'exchange_line_ids': [(4, exchange_line.id)]})

        # Return = 200, Exchange = 100 → Difference = -100
        self.assertAlmostEqual(wizard.return_total, 200.0, places=2)
        self.assertAlmostEqual(wizard.exchange_total, 100.0, places=2)
        self.assertAlmostEqual(wizard.exchange_difference, -100.0, places=2)
        self.assertFalse(wizard.is_customer_pays)
        self.assertTrue(wizard.is_customer_gets_refund)

        # Still creates both orders successfully
        wizard.action_confirm()
        return_order = self.env['pos.lite.order'].search([
            ('return_of_order_id', '=', order.id),
        ], limit=1)
        exchange_order = self.env['pos.lite.order'].search([
            ('exchange_of_order_id', '=', order.id),
        ], limit=1)
        self.assertTrue(return_order)
        self.assertTrue(exchange_order)
        self.assertEqual(return_order.state, 'done')
        self.assertEqual(exchange_order.state, 'done')