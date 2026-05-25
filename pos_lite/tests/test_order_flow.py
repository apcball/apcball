from odoo.tests import common, tagged
from odoo.exceptions import UserError


class TestOrderBase(common.TransactionCase):
    """Base class สร้างข้อมูลตั้งต้นที่ใช้ร่วมกันในทุก test ของ POS Lite"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        # Product category
        cls.category = cls.env['product.category'].create({
            'name': 'Test Category - POS Lite',
        })

        # Products — storable และ service
        cls.product_storable = cls.env['product.product'].create({
            'name': 'Test Storable Product',
            'type': 'product',
            'categ_id': cls.category.id,
            'sale_ok': True,
            'list_price': 100.0,
        })
        cls.product_service = cls.env['product.product'].create({
            'name': 'Test Service Product',
            'type': 'service',
            'categ_id': cls.category.id,
            'sale_ok': True,
            'list_price': 50.0,
        })

        # Partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer',
            'customer_rank': 1,
        })

        # Pricelist
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'Test Pricelist',
            'currency_id': cls.currency.id,
            'company_id': cls.company.id,
        })

        # Warehouse (default)
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.company.id),
        ], limit=1)
        if not cls.warehouse:
            cls.warehouse = cls.env['stock.warehouse'].create({
                'name': 'Test Warehouse',
                'code': 'TW',
                'company_id': cls.company.id,
            })

        # Account journals
        cls.sale_journal = cls.env['account.journal'].create({
            'name': 'Test Sale Journal',
            'type': 'sale',
            'code': 'TSJ',
            'company_id': cls.company.id,
        })
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'Test Cash Journal',
            'type': 'cash',
            'code': 'TCJ',
            'company_id': cls.company.id,
        })

        # Employee (no user_id to avoid UniqueViolation on hr_employee_user_uniq)
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Employee',
            'company_id': cls.company.id,
        })

        # POS Lite Config
        cls.config = cls.env['pos.lite.config'].create({
            'name': 'Test Config',
            'company_id': cls.company.id,
            'warehouse_id': cls.warehouse.id,
            'pricelist_id': cls.pricelist.id,
            'journal_id': cls.cash_journal.id,
        })

        # Advance sequences to avoid conflict with existing data in MOG_DEV
        cls.env.cr.execute("UPDATE ir_sequence SET number_next = 9000 WHERE code = 'pos.lite.session' AND number_next < 9000")
        cls.env.cr.execute("UPDATE ir_sequence SET number_next = 9000 WHERE code = 'pos.lite.order' AND number_next < 9000")

        # POS Lite Session (opened)
        cls.session = cls.env['pos.lite.session'].create({
            'config_id': cls.config.id,
            'employee_id': cls.employee.id,
            'company_id': cls.company.id,
        })

        # Tax 7%
        cls.tax = cls.env['account.tax'].create({
            'name': 'Test Tax 7%',
            'amount': 7.0,
            'amount_type': 'percent',
            'company_id': cls.company.id,
        })
        cls.product_storable.taxes_id = [(6, 0, cls.tax.ids)]
        cls.product_service.taxes_id = [(5, 0, 0)]  # ensure no tax

        # Stock — create quant so stock check passes
        stock_location = cls.warehouse.lot_stock_id
        cls.env['stock.quant'].create({
            'product_id': cls.product_storable.id,
            'location_id': stock_location.id,
            'quantity': 100.0,
        })

    def _create_draft_order(self, line_data=None):
        """Helper: สร้าง draft order พร้อม order lines"""
        if line_data is None:
            line_data = [(self.product_storable.id, 2, 100.0)]
        lines = [(0, 0, {
            'product_id': pid,
            'qty': qty,
            'price_unit': price,
        }) for pid, qty, price in line_data]
        return self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'channel': 'phone',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'line_ids': lines,
        })


@tagged('-at_install', 'post_install')
class TestOrderCreation(TestOrderBase):
    """ทดสอบการสร้าง Order ที่อยู่ในสถานะ draft"""

    def test_create_draft_order(self):
        """สร้าง order draft พร้อม 1 order line → ตรวจสอบ state=draft, มี line_ids"""
        order = self._create_draft_order()
        self.assertEqual(order.state, 'draft')
        self.assertEqual(len(order.line_ids), 1)
        self.assertEqual(order.channel, 'phone')
        self.assertTrue(order.name)
        self.assertTrue(order.session_id)

    def test_create_order_with_multiple_lines(self):
        """สร้าง order ที่มีทั้ง storable และ service product"""
        order = self._create_draft_order([
            (self.product_storable.id, 2, 100.0),
            (self.product_service.id, 1, 50.0),
        ])
        self.assertEqual(order.state, 'draft')
        self.assertEqual(len(order.line_ids), 2)


@tagged('-at_install', 'post_install')
class TestOrderComputation(TestOrderBase):
    """ทดสอบการคำนวณยอดเงินใน Order"""

    def test_amounts_without_tax(self):
        """service product ไม่มีภาษี → amount_tax=0, amount_untaxed = qty * price"""
        order = self._create_draft_order([
            (self.product_service.id, 3, 50.0),
        ])
        self.assertEqual(order.amount_untaxed, 150.0)
        self.assertEqual(order.amount_tax, 0.0)
        self.assertEqual(order.amount_total, 150.0)

    def test_amounts_with_tax(self):
        """storable product มีภาษี 7% → amount_tax = 7% ของ subtotal"""
        order = self._create_draft_order([
            (self.product_storable.id, 2, 100.0),
        ])
        expected_untaxed = 200.0
        expected_tax = 200.0 * 0.07  # 14.0
        expected_total = expected_untaxed + expected_tax
        self.assertEqual(order.amount_untaxed, expected_untaxed)
        self.assertAlmostEqual(order.amount_tax, expected_tax, places=2)
        self.assertEqual(order.amount_total, expected_total)

    def test_amounts_initial_zero(self):
        """order ใหม่ที่ยังไม่มี line → amount ทั้งหมดเป็น 0"""
        order = self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'channel': 'walkin',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
        })
        self.assertEqual(order.amount_untaxed, 0.0)
        self.assertEqual(order.amount_tax, 0.0)
        self.assertEqual(order.amount_total, 0.0)


@tagged('-at_install', 'post_install')
class TestOrderHoldResume(TestOrderBase):
    """ทดสอบ Hold / Resume Order"""

    def test_hold_and_resume(self):
        """draft → hold → resume → draft"""
        order = self._create_draft_order()
        order.action_hold()
        self.assertEqual(order.state, 'held')
        order.action_resume()
        self.assertEqual(order.state, 'draft')

    def test_hold_non_draft_should_fail(self):
        """hold เฉพาะ draft เท่านั้น — paid order ต้อง fail"""
        order = self._create_draft_order()
        # process ก่อน
        order.action_quick_pay_and_process()
        with self.assertRaises(UserError):
            order.action_hold()

    def test_resume_non_held_should_fail(self):
        """resume เฉพาะ held เท่านั้น"""
        order = self._create_draft_order()
        with self.assertRaises(UserError):
            order.action_resume()


@tagged('-at_install', 'post_install')
class TestOrderQuickPay(TestOrderBase):
    """ทดสอบ Quick Pay & Process"""

    def test_quick_pay_and_process(self):
        """quick pay → ตรวจสอบ invoice, picking, state=done"""
        order = self._create_draft_order([
            (self.product_storable.id, 1, 100.0),
            (self.product_service.id, 1, 50.0),
        ])
        result = order.action_quick_pay_and_process()
        self.assertTrue(result)
        order.invalidate_recordset()
        self.assertEqual(order.state, 'done')
        self.assertTrue(order.invoice_id)
        self.assertTrue(order.picking_id)
        self.assertEqual(order.invoice_id.state, 'posted')

    def test_quick_pay_already_paid(self):
        """order ที่ payment ครบแล้ว → quick pay ไม่สร้าง payment ซ้ำ"""
        order = self._create_draft_order([
            (self.product_service.id, 1, 50.0),
        ])
        # Register payment ก่อน
        self.env['pos.lite.payment'].create({
            'order_id': order.id,
            'payment_method': 'cash',
            'amount': 50.0,
            'journal_id': self.cash_journal.id,
        })
        result = order.action_quick_pay_and_process()
        self.assertTrue(result)
        self.assertEqual(order.state, 'done')

    def test_quick_pay_only_service(self):
        """service product เท่านั้น → ไม่มี picking แต่มี invoice"""
        order = self._create_draft_order([
            (self.product_service.id, 2, 50.0),
        ])
        order.action_quick_pay_and_process()
        self.assertEqual(order.state, 'done')
        self.assertTrue(order.invoice_id)
        # service product → ไม่สร้าง picking
        self.assertFalse(order.picking_id)


@tagged('-at_install', 'post_install')
class TestOrderValidation(TestOrderBase):
    """ทดสอบ validation error cases"""

    def test_process_without_lines_should_fail(self):
        """process order ที่ไม่มี line → ต้อง raise UserError"""
        order = self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'channel': 'walkin',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
        })
        with self.assertRaises(UserError):
            order.action_quick_pay_and_process()

    def test_process_without_payment_should_fail(self):
        """process order ที่มี line แต่ไม่มี payment → ต้อง raise UserError"""
        order = self._create_draft_order([
            (self.product_service.id, 1, 50.0),
        ])
        with self.assertRaises(UserError):
            order.action_process_order()

    def test_insufficient_stock_should_fail(self):
        """storable product ที่ stock ไม่พอ → ต้อง raise UserError"""
        order = self._create_draft_order([
            (self.product_storable.id, 999, 100.0),  # ต้องการ 999 ชิ้น แต่มีแค่ 100
        ])
        with self.assertRaises(UserError):
            order.action_quick_pay_and_process()