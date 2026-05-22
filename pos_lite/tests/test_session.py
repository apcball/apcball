# -*- coding: utf-8 -*-
from odoo.tests import common, tagged
from odoo.exceptions import UserError


class TestSessionBase(common.TransactionCase):
    """Base class สร้างข้อมูลตั้งต้นสำหรับทดสอบ session"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company

        # Product category + product
        cls.category = cls.env['product.category'].create({
            'name': 'Test Category - Session',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product',
            'type': 'service',
            'categ_id': cls.category.id,
            'sale_ok': True,
            'list_price': 100.0,
        })

        # Partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer',
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

        # Journal
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'Test Cash',
            'type': 'cash',
            'code': 'TCSH',
            'company_id': cls.company.id,
        })

        # Employee
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Emp',
            'user_id': cls.env.ref('base.user_admin').id,
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

    def _create_draft_order(self, session):
        """Helper: สร้าง draft order ใน session ที่กำหนด"""
        line = [(0, 0, {
            'product_id': self.product.id,
            'qty': 1,
            'price_unit': 100.0,
        })]
        return self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'channel': 'walkin',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'session_id': session.id,
            'line_ids': line,
        })


@tagged('-at_install', 'post_install')
class TestSessionOpenClose(TestSessionBase):
    """ทดสอบการเปิด-ปิด Session"""

    def test_create_session_opened(self):
        """สร้าง session → state=opened, มี date_open"""
        session = self.env['pos.lite.session'].create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        self.assertEqual(session.state, 'opened')
        self.assertTrue(session.date_open)
        self.assertTrue(session.name)

    def test_close_session(self):
        """open → close → state=closed, มี date_close"""
        session = self.env['pos.lite.session'].create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        session.action_close_session()
        self.assertEqual(session.state, 'closed')
        self.assertTrue(session.date_close)
        self.assertTrue(session.close_user_id)

    def test_close_already_closed_should_fail(self):
        """close session ที่ปิดไปแล้ว → ต้อง raise UserError"""
        session = self.env['pos.lite.session'].create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        session.action_close_session()
        with self.assertRaises(UserError):
            session.action_close_session()

    def test_reopen_session(self):
        """close → reopen → state=opened, date_close=False"""
        session = self.env['pos.lite.session'].create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        session.action_close_session()
        session.action_reopen_session()
        self.assertEqual(session.state, 'opened')
        self.assertFalse(session.date_close)
        self.assertFalse(session.close_user_id)

    def test_reopen_opened_session_should_fail(self):
        """reopen session ที่ยังเปิดอยู่ → ต้อง raise UserError"""
        session = self.env['pos.lite.session'].create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        with self.assertRaises(UserError):
            session.action_reopen_session()


@tagged('-at_install', 'post_install')
class TestSessionCloseWithDraftOrders(TestSessionBase):
    """ทดสอบการปิด Session ที่มี order ค้าง"""

    def test_close_with_draft_orders_should_fail(self):
        """close session ที่มี draft order → ต้อง raise UserError"""
        session = self.env['pos.lite.session'].create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        self._create_draft_order(session)
        with self.assertRaises(UserError):
            session.action_close_session()

    def test_close_with_held_orders_should_fail(self):
        """close session ที่มี held order → ต้อง raise UserError"""
        session = self.env['pos.lite.session'].create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        order = self._create_draft_order(session)
        order.action_hold()
        with self.assertRaises(UserError):
            session.action_close_session()

    def test_close_after_processing_all_orders(self):
        """process orders ทั้งหมดก่อน → close session สำเร็จ"""
        session = self.env['pos.lite.session'].create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        order = self._create_draft_order(session)
        order.action_quick_pay_and_process()
        # ตอนนี้ state=done หมดแล้ว
        session.action_close_session()
        self.assertEqual(session.state, 'closed')


@tagged('-at_install', 'post_install')
class TestSessionStats(TestSessionBase):
    """ทดสอบการคำนวณสถิติของ Session"""

    def test_stats_empty_session(self):
        """session เปล่า → จำนวน 0"""
        session = self.env['pos.lite.session'].create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        self.assertEqual(session.order_count, 0)
        self.assertEqual(session.amount_total, 0.0)

    def test_stats_after_sale(self):
        """session ที่มี order done → stats แสดงยอดขาย"""
        session = self.env['pos.lite.session'].create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        order = self._create_draft_order(session)
        order.action_quick_pay_and_process()
        session.invalidate_recordset()
        self.assertEqual(session.order_count_sales, 1)
        self.assertEqual(session.order_count, 1)
        self.assertEqual(session.amount_total, 100.0)

    def test_stats_excludes_draft(self):
        """session ที่มี draft order ไม่นับรวมใน stats"""
        session = self.env['pos.lite.session'].create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        self._create_draft_order(session)
        session.invalidate_recordset()
        self.assertEqual(session.order_count, 0)
        self.assertEqual(session.amount_total, 0.0)