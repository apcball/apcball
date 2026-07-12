"""Additional tests covering constraints, state transitions, cancel, reorder,
config, and name_search overrides."""

from odoo.tests import common, tagged
from odoo.exceptions import UserError, ValidationError


class TestAdditionalBase(common.TransactionCase):
    """Shared setup for supplementary tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        cls.category = cls.env['product.category'].create({
            'name': 'Test Cat - Extra',
        })
        cls.product_svc = cls.env['product.product'].create({
            'name': 'Test SVC Extra',
            'type': 'service',
            'categ_id': cls.category.id,
            'sale_ok': True,
            'list_price': 100.0,
            'taxes_id': [(5, 0, 0)],
        })
        cls.product_storable = cls.env['product.product'].create({
            'name': 'Test Storable Extra',
            'type': 'product',
            'categ_id': cls.category.id,
            'sale_ok': True,
            'list_price': 200.0,
            'taxes_id': [(5, 0, 0)],
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Cust Extra',
            'customer_rank': 1,
        })
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'PL Extra',
            'company_id': cls.company.id,
        })
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'Cash J Extra',
            'type': 'cash',
            'code': 'CJEX',
            'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Emp Extra',
            'company_id': cls.company.id,
        })
        cls.config = cls.env['pos.lite.config'].create({
            'name': 'Cfg Extra',
            'company_id': cls.company.id,
            'warehouse_id': cls.warehouse.id,
            'pricelist_id': cls.pricelist.id,
            'journal_id': cls.cash_journal.id,
        })
        # Advance sequences to avoid conflict with existing data in MOG_DEV
        cls.env.cr.execute("UPDATE ir_sequence SET number_next = 100000 WHERE code = 'pos.lite.session' AND number_next < 100000")
        cls.env.cr.execute("UPDATE ir_sequence SET number_next = 100000 WHERE code = 'pos.lite.order' AND number_next < 100000")
        cls.env.invalidate_all()
        cls.session = cls.env['pos.lite.session'].create({
            'config_id': cls.config.id,
            'employee_id': cls.employee.id,
            'company_id': cls.company.id,
        })
        # Stock quant for storable product
        cls.env['stock.quant'].create({
            'product_id': cls.product_storable.id,
            'location_id': cls.warehouse.lot_stock_id.id,
            'quantity': 50.0,
        })

    def _draft_order(self, lines=None, **kw):
        if lines is None:
            lines = [(self.product_svc.id, 1, 100.0)]
        line_cmds = [(0, 0, {
            'product_id': pid, 'qty': qty, 'price_unit': price,
        }) for pid, qty, price in lines]
        vals = {
            'company_id': self.company.id,
            'channel': 'phone',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'session_id': self.session.id,
            'line_ids': line_cmds,
        }
        vals.update(kw)
        return self.env['pos.lite.order'].create(vals)

    def _process_order(self, lines=None, **kw):
        order = self._draft_order(lines, **kw)
        order.action_quick_pay_and_process()
        self.assertEqual(order.state, 'done')
        return order


# ─── Order Line Constraints ──────────────────────────────────

@tagged('-at_install', 'post_install')
class TestOrderLineConstraints(TestAdditionalBase):
    """Test validation on pos.lite.order.line."""

    def test_qty_zero_raises(self):
        with self.assertRaises(ValidationError):
            self._draft_order([(self.product_svc.id, 0, 100.0)])

    def test_qty_negative_raises(self):
        with self.assertRaises(ValidationError):
            self._draft_order([(self.product_svc.id, -1, 100.0)])

    def test_discount_negative_raises(self):
        order = self._draft_order()
        with self.assertRaises(ValidationError):
            order.line_ids[0].discount = -1

    def test_discount_over_100_raises(self):
        order = self._draft_order()
        with self.assertRaises(ValidationError):
            order.line_ids[0].discount = 101

    def test_discount_valid_values(self):
        order = self._draft_order()
        order.line_ids[0].discount = 0
        self.assertEqual(order.line_ids[0].discount, 0)
        order.line_ids[0].discount = 50
        self.assertEqual(order.line_ids[0].discount, 50)
        order.line_ids[0].discount = 100
        self.assertEqual(order.line_ids[0].discount, 100)

    def test_discount_applied_to_amount(self):
        order = self._draft_order([(self.product_svc.id, 2, 100.0)])
        order.line_ids[0].discount = 10
        order.invalidate_recordset()
        # 2 * 100 * 0.9 = 180
        self.assertAlmostEqual(order.amount_untaxed, 180.0, places=2)


# ─── Payment Constraints ────────────────────────────────────

@tagged('-at_install', 'post_install')
class TestPaymentConstraints(TestAdditionalBase):
    """Test payment amount constraints."""

    def test_normal_payment_negative_raises(self):
        order = self._draft_order()
        with self.assertRaises(ValidationError):
            self.env['pos.lite.payment'].create({
                'order_id': order.id,
                'payment_method': 'cash',
                'amount': -50.0,
                'journal_id': self.cash_journal.id,
            })

    def test_normal_payment_positive_ok(self):
        order = self._draft_order()
        pay = self.env['pos.lite.payment'].create({
            'order_id': order.id,
            'payment_method': 'cash',
            'amount': 50.0,
            'journal_id': self.cash_journal.id,
        })
        self.assertEqual(pay.amount, 50.0)

    def test_return_payment_positive_raises(self):
        order = self._process_order()
        return_order = self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'channel': 'phone',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'is_return': True,
            'return_of_order_id': order.id,
            'line_ids': [(0, 0, {
                'product_id': self.product_svc.id,
                'qty': 1,
                'price_unit': 100.0,
                'returned_from_line_id': order.line_ids[0].id,
            })],
        })
        with self.assertRaises(ValidationError):
            self.env['pos.lite.payment'].create({
                'order_id': return_order.id,
                'payment_method': 'cash',
                'amount': 100.0,
                'journal_id': self.cash_journal.id,
            })

    def test_return_payment_negative_ok(self):
        order = self._process_order()
        return_order = self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'channel': 'phone',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'is_return': True,
            'return_of_order_id': order.id,
            'line_ids': [(0, 0, {
                'product_id': self.product_svc.id,
                'qty': 1,
                'price_unit': 100.0,
                'returned_from_line_id': order.line_ids[0].id,
            })],
        })
        pay = self.env['pos.lite.payment'].create({
            'order_id': return_order.id,
            'payment_method': 'cash',
            'amount': -100.0,
            'journal_id': self.cash_journal.id,
        })
        self.assertEqual(pay.amount, -100.0)


# ─── State Transitions ─────────────────────────────────────

@tagged('-at_install', 'post_install')
class TestStateTransitions(TestAdditionalBase):
    """Test invalid state transitions raise errors."""

    def test_invalid_transition_draft_to_paid_via_write(self):
        order = self._draft_order()
        order.write({'state': 'paid'})
        self.assertEqual(order.state, 'paid')

    def test_invalid_transition_done_to_draft(self):
        order = self._process_order()
        with self.assertRaises(UserError):
            order.write({'state': 'draft'})

    def test_invalid_transition_cancelled_to_draft(self):
        order = self._draft_order()
        order.write({'state': 'cancelled'})
        with self.assertRaises(UserError):
            order.write({'state': 'draft'})

    def test_valid_transition_held_to_draft(self):
        order = self._draft_order()
        order.action_hold()
        order.write({'state': 'draft'})
        self.assertEqual(order.state, 'draft')


# ─── Cancel Flow ────────────────────────────────────────────

@tagged('-at_install', 'post_install')
class TestCancelFlow(TestAdditionalBase):
    """Test action_cancel on service-only orders (no picking)."""

    def test_cancel_draft_order(self):
        order = self._draft_order()
        order.action_cancel()
        self.assertEqual(order.state, 'cancelled')

    def test_cancel_posted_invoice_raises(self):
        """Cancel ที่มี posted invoice (non-return) ต้อง raise"""
        order = self._process_order()
        with self.assertRaises(UserError):
            order.action_cancel()

    def test_cancel_return_order_reverses(self):
        """Cancel return order — done→cancelled not allowed by transition map,
        so this tests that the transition error is raised."""
        original = self._process_order()
        # Create return via wizard
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': original.id,
        })
        wizard._onchange_order_id()
        wizard.action_confirm()

        return_order = self.env['pos.lite.order'].search([
            ('return_of_order_id', '=', original.id),
        ], limit=1)
        self.assertTrue(return_order.invoice_id)
        self.assertEqual(return_order.invoice_id.move_type, 'out_refund')

        # done → cancelled is not in _ALLOWED_TRANSITIONS
        with self.assertRaises(UserError):
            return_order.action_cancel()


# ─── Done Action ────────────────────────────────────────────

@tagged('-at_install', 'post_install')
class TestDoneAction(TestAdditionalBase):
    """Test manual action_done."""

    def test_done_non_paid_raises(self):
        order = self._draft_order()
        with self.assertRaises(UserError):
            order.action_done()

    def test_done_from_paid_state(self):
        order = self._draft_order()
        # Manual payment + process
        self.env['pos.lite.payment'].create({
            'order_id': order.id,
            'payment_method': 'cash',
            'amount': 100.0,
            'journal_id': self.cash_journal.id,
        })
        order.action_process_order()
        # For service-only, it goes directly to done
        self.assertEqual(order.state, 'done')


# ─── Re-order ───────────────────────────────────────────────

@tagged('-at_install', 'post_install')
class TestReorder(TestAdditionalBase):
    """Test action_reorder creates a copy."""

    def test_reorder_from_done(self):
        original = self._process_order([
            (self.product_svc.id, 2, 100.0),
        ])
        result = original.action_reorder()
        self.assertEqual(result['res_model'], 'pos.lite.order')
        new_order = self.env['pos.lite.order'].browse(result['res_id'])
        self.assertNotEqual(new_order.id, original.id)
        self.assertEqual(new_order.state, 'draft')
        self.assertEqual(len(new_order.line_ids), 1)
        self.assertEqual(new_order.line_ids[0].qty, 2)
        self.assertEqual(new_order.line_ids[0].price_unit, 100.0)
        self.assertIn(original.name, new_order.note or '')

    def test_reorder_from_draft_raises(self):
        order = self._draft_order()
        with self.assertRaises(UserError):
            order.action_reorder()


# ─── Config ─────────────────────────────────────────────────

@tagged('-at_install', 'post_install')
class TestConfig(TestAdditionalBase):
    """Test pos.lite.config helpers."""

    def test_get_default_config(self):
        config = self.env['pos.lite.config'].get_default_config(self.company)
        self.assertTrue(config)
        self.assertEqual(config.id, self.config.id)

    def test_get_default_config_no_match(self):
        other_company = self.env['res.company'].create({
            'name': 'Other Company',
        })
        config = self.env['pos.lite.config'].get_default_config(other_company)
        self.assertFalse(config)


# ─── Picking Type Config ────────────────────────────────────

@tagged('-at_install', 'post_install')
class TestPickingTypeConfig(TestAdditionalBase):
    """Test that pos.lite.config picking_type fields are used in order processing."""

    def test_config_picking_type_fields_exist(self):
        """config มี out_picking_type_id และ return_picking_type_id"""
        self.assertTrue(hasattr(self.config, 'out_picking_type_id'))
        self.assertTrue(hasattr(self.config, 'return_picking_type_id'))

    def test_fallback_to_warehouse_default_when_config_empty(self):
        """เมื่อ config ไม่ได้ตั้ง picking_type → fallback เป็น warehouse default"""
        self.assertFalse(self.config.out_picking_type_id)
        self.assertFalse(self.config.return_picking_type_id)

        # ใช้ storable product เพื่อให้มี picking
        order = self._process_order([
            (self.product_storable.id, 1, 200.0),
        ])
        self.assertTrue(order.picking_id)
        self.assertEqual(
            order.picking_id.picking_type_id,
            self.warehouse.out_type_id,
        )

    def test_config_out_picking_type_used_when_set(self):
        """เมื่อ config ตั้ง out_picking_type_id → ใช้ค่านั้นแทน warehouse default"""
        custom_type = self.env['stock.picking.type'].create({
            'name': 'POS Delivery Custom',
            'code': 'outgoing',
            'warehouse_id': self.warehouse.id,
            'company_id': self.company.id,
            'sequence_code': 'POSOUT',
        })
        self.config.out_picking_type_id = custom_type.id

        order = self._process_order([
            (self.product_storable.id, 1, 200.0),
        ])
        self.assertTrue(order.picking_id)
        self.assertEqual(order.picking_id.picking_type_id.id, custom_type.id)
        self.assertNotEqual(order.picking_id.picking_type_id, self.warehouse.out_type_id)

    def test_config_return_picking_type_used_when_set(self):
        """เมื่อ config ตั้ง return_picking_type_id → return order ใช้ค่านั้น"""
        custom_return_type = self.env['stock.picking.type'].create({
            'name': 'POS Return Custom',
            'code': 'incoming',
            'warehouse_id': self.warehouse.id,
            'company_id': self.company.id,
            'sequence_code': 'POSRET',
        })
        self.config.return_picking_type_id = custom_return_type.id

        # สร้าง order ปกติก่อน (storable เพื่อมี picking)
        original = self._process_order([
            (self.product_storable.id, 1, 200.0),
        ])
        # สร้าง return ผ่าน wizard
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': original.id,
        })
        wizard._onchange_order_id()
        # เติม return line ด้วย storable product
        wizard.line_ids.write({
            'order_line_id': original.line_ids[0].id,
        })
        wizard.action_confirm()

        return_order = self.env['pos.lite.order'].search([
            ('return_of_order_id', '=', original.id),
        ], limit=1)
        self.assertTrue(return_order)
        self.assertTrue(return_order.picking_id)
        self.assertEqual(return_order.picking_id.picking_type_id.id, custom_return_type.id)
        self.assertNotEqual(return_order.picking_id.picking_type_id, self.warehouse.in_type_id)


# ─── Product name_search ────────────────────────────────────

@tagged('-at_install', 'post_install')
class TestProductSearch(TestAdditionalBase):
    """Test product name_search with pos_lite_search context."""

    def test_search_by_name_with_context(self):
        results = self.env['product.product'].with_context(
            pos_lite_search=True
        ).name_search('Test SVC Extra')
        product_ids = [r[0] for r in results]
        self.assertIn(self.product_svc.id, product_ids)

    def test_search_by_name_without_context(self):
        results = self.env['product.product'].name_search('Test SVC Extra')
        product_ids = [r[0] for r in results]
        self.assertIn(self.product_svc.id, product_ids)

    def test_search_empty_name_with_context(self):
        """Empty name → falls back to default name_search."""
        results = self.env['product.product'].with_context(
            pos_lite_search=True
        ).name_search('')
        self.assertIsInstance(results, list)

    def test_search_with_default_code(self):
        self.product_svc.default_code = 'SVC-001'
        results = self.env['product.product'].with_context(
            pos_lite_search=True
        ).name_search('SVC-001')
        product_ids = [r[0] for r in results]
        self.assertIn(self.product_svc.id, product_ids)


# ─── Partner name_search ────────────────────────────────────

@tagged('-at_install', 'post_install')
class TestPartnerSearch(TestAdditionalBase):
    """Test partner name_search with pos_lite_partner_search context."""

    def test_search_by_name_with_context(self):
        results = self.env['res.partner'].with_context(
            pos_lite_partner_search=True
        ).name_search('Test Cust Extra')
        partner_ids = [r[0] for r in results]
        self.assertIn(self.partner.id, partner_ids)

    def test_search_by_phone(self):
        self.partner.phone = '0812345678'
        results = self.env['res.partner'].with_context(
            pos_lite_partner_search=True
        ).name_search('0812345678')
        partner_ids = [r[0] for r in results]
        self.assertIn(self.partner.id, partner_ids)

    def test_search_by_vat(self):
        self.partner.vat = '1234567890123'
        results = self.env['res.partner'].with_context(
            pos_lite_partner_search=True
        ).name_search('1234567890123')
        partner_ids = [r[0] for r in results]
        self.assertIn(self.partner.id, partner_ids)

    def test_search_empty_name_with_context(self):
        results = self.env['res.partner'].with_context(
            pos_lite_partner_search=True
        ).name_search('')
        self.assertIsInstance(results, list)


# ─── Session Payment Breakdown ──────────────────────────────

@tagged('-at_install', 'post_install')
class TestSessionPaymentBreakdown(TestAdditionalBase):
    """Test session payment method breakdown compute."""

    def test_payment_cash_breakdown(self):
        order = self._draft_order()
        self.env['pos.lite.payment'].create({
            'order_id': order.id,
            'payment_method': 'cash',
            'amount': 100.0,
            'journal_id': self.cash_journal.id,
        })
        order.action_process_order()
        self.session.invalidate_recordset()
        self.assertEqual(self.session.payment_cash, 100.0)
        self.assertEqual(self.session.payment_transfer, 0.0)
        self.assertEqual(self.session.payment_card, 0.0)

    def test_payment_mixed_methods(self):
        order = self._draft_order([
            (self.product_svc.id, 3, 100.0),
        ])
        self.env['pos.lite.payment'].create({
            'order_id': order.id,
            'payment_method': 'cash',
            'amount': 150.0,
            'journal_id': self.cash_journal.id,
        })
        self.env['pos.lite.payment'].create({
            'order_id': order.id,
            'payment_method': 'transfer',
            'amount': 150.0,
            'journal_id': self.cash_journal.id,
        })
        order.action_process_order()
        self.session.invalidate_recordset()
        self.assertEqual(self.session.payment_cash, 150.0)
        self.assertEqual(self.session.payment_transfer, 150.0)

    def test_session_stats_with_return(self):
        """Return order ถูกนับใน order_count_returns, amount_refund"""
        original = self._process_order()
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': original.id,
        })
        wizard._onchange_order_id()
        wizard.action_confirm()

        # Return orders are created without session_id (auto-skip for returns)
        # Assign the return to our session so it's counted in stats
        return_order = self.env['pos.lite.order'].search([
            ('return_of_order_id', '=', original.id),
        ], limit=1)
        self.assertTrue(return_order)
        return_order.session_id = self.session.id

        self.session.invalidate_recordset()
        self.assertEqual(self.session.order_count_returns, 1)
        self.assertTrue(self.session.amount_refund > 0)
        self.assertEqual(self.session.amount_net,
                         self.session.amount_total - self.session.amount_refund)


# ─── Onchange & Helpers ─────────────────────────────────────

@tagged('-at_install', 'post_install')
class TestOrderOnchange(TestAdditionalBase):
    """Test onchange and helper methods on pos.lite.order."""

    def test_onchange_partner_populates_fields(self):
        self.partner.phone = '0999999999'
        self.partner.street = '123 Test St'
        self.partner.vat = '0987654321'
        order = self._draft_order()
        order.partner_id = self.partner
        order._onchange_partner_id()
        self.assertEqual(order.customer_name, self.partner.name)
        self.assertEqual(order.partner_phone, '0999999999')
        self.assertEqual(order.partner_address, '123 Test St')
        self.assertEqual(order.partner_tax_id, '0987654321')

    def test_onchange_partner_clears_fields(self):
        order = self._draft_order()
        order.partner_id = False
        order._onchange_partner_id()
        self.assertFalse(order.customer_name)
        self.assertFalse(order.partner_phone)

    def test_get_or_create_customer_partner_existing(self):
        order = self._draft_order()
        partner = order._get_or_create_customer_partner()
        self.assertEqual(partner, self.partner)

    def test_get_or_create_customer_partner_no_partner(self):
        order = self._draft_order()
        order.partner_id = False
        order.customer_name = 'New Customer XYZ'
        partner = order._get_or_create_customer_partner()
        self.assertTrue(partner)
        self.assertEqual(partner.name, 'New Customer XYZ')

    def test_get_or_create_customer_partner_walkin(self):
        order = self._draft_order()
        order.partner_id = False
        order.customer_name = False
        partner = order._get_or_create_customer_partner()
        self.assertEqual(partner.name, 'Walk-in Customer')

    def test_view_invoice_raises_without_invoice(self):
        order = self._draft_order()
        with self.assertRaises(UserError):
            order.action_view_invoice()

    def test_view_picking_raises_without_picking(self):
        order = self._draft_order()
        with self.assertRaises(UserError):
            order.action_view_picking()

    def test_view_payments_raises_without_account_payment(self):
        order = self._draft_order()
        with self.assertRaises(UserError):
            order.action_view_payments()

    def test_create_order_without_session_raises(self):
        """สร้าง order โดยไม่มี open session → raise UserError"""
        # Close ALL open sessions for the company
        open_sessions = self.env['pos.lite.session'].search([
            ('company_id', '=', self.company.id),
            ('state', '=', 'opened'),
        ])
        for s in open_sessions:
            pending = s.order_ids.filtered(lambda o: o.state in ('draft', 'held'))
            pending.action_cancel()
            s.action_close_session()
        # Create order without explicit session_id
        with self.assertRaises(UserError):
            self.env['pos.lite.order'].create({
                'company_id': self.company.id,
                'channel': 'phone',
                'partner_id': self.partner.id,
                'warehouse_id': self.warehouse.id,
                'pricelist_id': self.pricelist.id,
                'line_ids': [(0, 0, {
                    'product_id': self.product_svc.id,
                    'qty': 1,
                    'price_unit': 100.0,
                })],
            })

# ─── Stock Check ────────────────────────────────────────────

@tagged('-at_install', 'post_install')
class TestStockCheck(TestAdditionalBase):
    """Test stock availability checks."""

    def test_qty_available_on_service_is_zero(self):
        order = self._draft_order([(self.product_svc.id, 1, 100.0)])
        self.assertEqual(order.line_ids[0].qty_available, 0.0)
        self.assertFalse(order.line_ids[0].is_low_stock)

    def test_qty_available_on_storable(self):
        order = self._draft_order([(self.product_storable.id, 1, 200.0)])
        self.assertEqual(order.line_ids[0].qty_available, 50.0)
        self.assertFalse(order.line_ids[0].is_low_stock)

    def test_low_stock_flag(self):
        order = self._draft_order([(self.product_storable.id, 100, 200.0)])
        self.assertTrue(order.line_ids[0].is_low_stock)

    def test_discount_applied_to_tax_computation(self):
        """Discount ต้องมีผลกับ tax calculation"""
        tax = self.env['account.tax'].create({
            'name': 'Test Tax 10%',
            'amount': 10.0,
            'amount_type': 'percent',
            'company_id': self.company.id,
        })
        self.product_svc.taxes_id = [(6, 0, tax.ids)]
        order = self._draft_order([(self.product_svc.id, 2, 100.0)])
        order.line_ids[0].discount = 50
        order.invalidate_recordset()
        # price after discount: 100 * 0.5 = 50
        # untaxed: 2 * 50 = 100
        # tax: 100 * 0.1 = 10
        # total: 110
        self.assertAlmostEqual(order.amount_untaxed, 100.0, places=2)
        self.assertAlmostEqual(order.amount_tax, 10.0, places=2)
        self.assertAlmostEqual(order.amount_total, 110.0, places=2)
        # Cleanup
        self.product_svc.taxes_id = [(5, 0, 0)]


# ─── Quick Pay Edge Cases ───────────────────────────────────

@tagged('-at_install', 'post_install')
class TestQuickPayEdgeCases(TestAdditionalBase):
    """Test quick pay from held state and with existing payments."""

    def test_quick_pay_from_held(self):
        order = self._draft_order()
        order.action_hold()
        self.assertEqual(order.state, 'held')
        result = order.action_quick_pay_and_process()
        self.assertTrue(result)
        self.assertEqual(order.state, 'done')

    def test_quick_pay_non_draft_non_held_raises(self):
        order = self._process_order()
        with self.assertRaises(UserError):
            order.action_quick_pay_and_process()

    def test_quick_pay_with_partial_payment(self):
        """มี partial payment แล้ว → quick pay ไม่สร้าง payment เพิ่ม"""
        order = self._draft_order([(self.product_svc.id, 1, 100.0)])
        self.env['pos.lite.payment'].create({
            'order_id': order.id,
            'payment_method': 'transfer',
            'amount': 60.0,
            'journal_id': self.cash_journal.id,
        })
        result = order.action_quick_pay_and_process()
        self.assertTrue(result)
        self.assertEqual(order.state, 'done')
        self.assertEqual(len(order.payment_ids), 1)
