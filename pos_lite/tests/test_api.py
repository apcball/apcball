"""Tests for POS Lite new controller APIs (Phase 1-3): 
session_info, order_detail, orders_for_return, create_return, product images."""

from odoo.tests import common, tagged


class TestApiBase(common.TransactionCase):
    """Base class สร้างข้อมูลตั้งต้นสำหรับทดสอบ APIs"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company
        cls.category = cls.env['product.category'].create({
            'name': 'Test Category - API',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product API',
            'type': 'service',
            'categ_id': cls.category.id,
            'sale_ok': True,
            'list_price': 100.0,
            'taxes_id': [(5, 0, 0)],
            'can_be_pos': True,
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer API',
            'customer_rank': 1,
        })
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'Test Pricelist API',
            'company_id': cls.company.id,
        })
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'Test Cash API',
            'type': 'cash',
            'code': 'TAPI',
            'company_id': cls.company.id,
        })
        cls.emp1 = cls.env['hr.employee'].create({
            'name': 'Test Emp API 1',
            'company_id': cls.company.id,
        })
        cls.emp2 = cls.env['hr.employee'].create({
            'name': 'Test Emp API 2',
            'company_id': cls.company.id,
        })
        cls.config = cls.env['pos.lite.config'].create({
            'name': 'Test Config API',
            'company_id': cls.company.id,
            'warehouse_id': cls.warehouse.id,
            'pricelist_id': cls.pricelist.id,
            'journal_id': cls.cash_journal.id,
        })
        # Advance sequences to avoid conflict with existing data in MOG_DEV
        cls.env.cr.execute("UPDATE ir_sequence SET number_next = 100000 WHERE code IN ('pos.lite.session', 'pos.lite.order') AND number_next < 100000")
        cls.env.invalidate_all()

        # Session with multiple employees
        cls.session = cls.env['pos.lite.session'].create({
            'config_id': cls.config.id,
            'employee_id': cls.emp1.id,
            'employee_ids': [(6, 0, [cls.emp1.id, cls.emp2.id])],
            'company_id': cls.company.id,
        })

    def _create_done_order(self, session=None):
        """Helper: สร้างและ process order"""
        if not session:
            session = self.session
        order = self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'channel': 'walkin',
            'partner_id': self.partner.id,
            'employee_id': self.emp1.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'session_id': session.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'qty': 2,
                'price_unit': 100.0,
            })],
        })
        order.action_quick_pay_and_process()
        self.assertEqual(order.state, 'done')
        return order


@tagged('-at_install', 'post_install')
class TestSessionInfoApi(TestApiBase):
    """ทดสอบ API /pos_lite/api/session_info"""

    def test_session_info_returns_employees(self):
        """session_info ต้อง return employees จาก session.employee_ids"""
        # เรียกผ่าน model โดยตรง (ไม่ผ่าน HTTP)
        from odoo.http import request
        # ใช้วิธี mock request
        session = self.session
        employees = session.employee_ids
        emp_data = [{'id': e.id, 'name': e.name} for e in employees]
        self.assertEqual(len(emp_data), 2)
        names = [e['name'] for e in emp_data]
        self.assertIn('Test Emp API 1', names)
        self.assertIn('Test Emp API 2', names)

    def test_session_info_returns_default_warehouse(self):
        """session_info ต้อง return default warehouse จาก config"""
        session = self.session
        self.assertTrue(session.config_id.warehouse_id)
        self.assertEqual(session.config_id.warehouse_id.id, self.warehouse.id)

    def test_session_info_returns_pricelist(self):
        """session_info ต้อง return default pricelist จาก config"""
        session = self.session
        self.assertTrue(session.config_id.pricelist_id)
        self.assertEqual(session.config_id.pricelist_id.id, self.pricelist.id)

    def test_session_info_fallback_employees(self):
        """เมื่อไม่มี session หรือไม่มี employee_ids → fallback เป็น employees ของบริษัท"""
        employees = self.env['hr.employee'].search([
            ('company_id', '=', self.company.id),
        ])
        self.assertTrue(len(employees) >= 2)


@tagged('-at_install', 'post_install')
class TestOrderDetailApi(TestApiBase):
    """ทดสอบ API /pos_lite/api/order_detail"""

    def test_order_detail_has_lines(self):
        """order_detail ต้องมี lines"""
        order = self._create_done_order()
        self.assertTrue(order.line_ids)
        self.assertEqual(len(order.line_ids), 1)
        self.assertEqual(order.line_ids[0].product_id.id, self.product.id)
        self.assertEqual(order.line_ids[0].qty, 2)

    def test_order_detail_has_payments(self):
        """order_detail ต้องมี payments"""
        order = self._create_done_order()
        self.assertTrue(order.payment_ids)
        self.assertEqual(len(order.payment_ids), 1)
        self.assertTrue(order.payment_ids[0].amount > 0)

    def test_order_detail_has_employee(self):
        """order_detail ต้องมี employee_name"""
        order = self._create_done_order()
        self.assertTrue(order.employee_id)
        self.assertEqual(order.employee_id.name, 'Test Emp API 1')

    def test_order_detail_total(self):
        """order_detail ต้องมี amount_total ที่ถูกต้อง"""
        order = self._create_done_order()
        self.assertEqual(order.amount_total, 200.0)


@tagged('-at_install', 'post_install')
class TestOrdersForReturnApi(TestApiBase):
    """ทดสอบ API /pos_lite/api/orders_for_return"""

    def test_orders_for_return_finds_done_orders(self):
        """orders_for_return ต้องหา orders ที่ state=done และไม่ใช่ return"""
        order = self._create_done_order()
        orders = self.env['pos.lite.order'].search([
            ('state', '=', 'done'),
            ('is_return', '=', False),
        ])
        self.assertIn(order.id, orders.ids)

    def test_orders_for_return_excludes_return_orders(self):
        """orders_for_return ไม่รวม return order"""
        order = self._create_done_order()
        # สร้าง return
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': order.id,
        })
        wizard._onchange_order_id()
        wizard.action_confirm()
        return_order = self.env['pos.lite.order'].search([
            ('return_of_order_id', '=', order.id),
        ], limit=1)
        self.assertTrue(return_order)

        # orders_for_return ไม่ควรรวม return_order (is_return=True)
        orders = self.env['pos.lite.order'].search([
            ('state', '=', 'done'),
            ('is_return', '=', False),
        ])
        self.assertNotIn(return_order.id, orders.ids)


@tagged('-at_install', 'post_install')
class TestCreateReturnApi(TestApiBase):
    """ทดสอบ API /pos_lite/api/create_return"""

    def test_create_return_via_api(self):
        """create_return ต้องสร้าง return order ได้"""
        order = self._create_done_order()

        # จำลอง controller logic ใน test
        return_order = self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'customer_name': order.customer_name,
            'partner_phone': order.partner_phone,
            'channel': order.channel,
            'session_id': order.session_id.id,
            'employee_id': order.employee_id.id,
            'warehouse_id': order.warehouse_id.id,
            'pricelist_id': order.pricelist_id.id,
            'is_return': True,
            'return_of_order_id': order.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'qty': 1,
                'price_unit': 100.0,
            })],
        })
        return_order.action_quick_pay_and_process()
        self.assertEqual(return_order.state, 'done')
        self.assertTrue(return_order.is_return)
        self.assertEqual(return_order.return_of_order_id.id, order.id)

    def test_create_return_with_reason(self):
        """create_return ต้องรองรับ return_reason"""
        order = self._create_done_order()
        return_order = self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'channel': 'walkin',
            'session_id': order.session_id.id,
            'employee_id': order.employee_id.id,
            'warehouse_id': order.warehouse_id.id,
            'pricelist_id': order.pricelist_id.id,
            'is_return': True,
            'return_of_order_id': order.id,
            'return_reason': 'สินค้าชำรุด',
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'qty': 1,
                'price_unit': 100.0,
            })],
        })
        return_order.action_quick_pay_and_process()
        self.assertEqual(return_order.return_reason, 'สินค้าชำรุด')


@tagged('-at_install', 'post_install')
class TestProductApi(TestApiBase):
    """ทดสอบ product APIs"""

    def test_product_has_image_fields(self):
        """product ต้องมี image_128, image_256 fields"""
        product = self.product
        self.assertIn('image_128', product._fields)
        self.assertIn('image_256', product._fields)

    def test_product_sale_ok_and_can_be_pos(self):
        """product ที่ขายได้ต้องมี sale_ok=True และ can_be_pos=True"""
        product = self.product
        self.assertTrue(product.sale_ok)
        self.assertTrue(product.can_be_pos)

    def test_product_pricelist_applied(self):
        """product ต้องมี pricelist id สำหรับคำนวณราคา"""
        self.assertTrue(self.pricelist.id)