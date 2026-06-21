from odoo.tests import tagged
from odoo.exceptions import UserError, AccessError
from odoo.addons.sale.tests.common import TestSaleCommon


@tagged('at_install', 'post_install')
class TestForceInvoice(TestSaleCommon):

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref)
        cls.env.user.groups_id += cls.env.ref(
            'buz_sale_force_invoice.group_force_invoice_manager',
        )
        income_account = cls.env['account.account'].search([
            ('account_type', '=', 'income'),
        ], limit=1)
        expense_account = cls.env['account.account'].search([
            ('account_type', '=', 'expense'),
        ], limit=1)
        if not income_account:
            income_account = cls.env['account.account'].create({
                'name': 'Test Income',
                'code': '400000',
                'account_type': 'income',
            })
        if not expense_account:
            expense_account = cls.env['account.account'].create({
                'name': 'Test Expense',
                'code': '500000',
                'account_type': 'expense',
            })
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product',
            'type': 'product',
            'invoice_policy': 'delivery',
            'list_price': 100.0,
            'property_account_income_id': income_account.id,
            'property_account_expense_id': expense_account.id,
            'taxes_id': [(5, 0, 0)],
            'supplier_taxes_id': [(5, 0, 0)],
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer',
        })

    def _create_sale_order(self, qty=10, price=100.0):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'partner_invoice_id': self.partner.id,
            'partner_shipping_id': self.partner.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product.id,
                    'product_uom_qty': qty,
                    'price_unit': price,
                }),
            ],
        })
        order.action_confirm()
        return order

    def test_01_force_invoice_creates_invoice(self):
        """Create invoice for undelivered SO with delivery policy."""
        order = self._create_sale_order(qty=10, price=100.0)
        self.assertEqual(
            order.order_line.qty_delivered, 0.0,
            "No delivery should exist",
        )
        wizard = self.env['sale.force.invoice.wizard'].create({
            'sale_order_id': order.id,
            'reason': 'customer_request',
            'note': 'Urgent billing for LC process',
        })
        result = wizard.action_confirm()

        self.assertTrue(order.force_invoice)
        self.assertEqual(order.force_invoice_reason, 'customer_request')
        self.assertEqual(order.force_invoice_note, 'Urgent billing for LC process')
        self.assertEqual(order.force_invoice_user_id, self.env.user)
        self.assertTrue(order.force_invoice_date)
        self.assertEqual(len(order.invoice_ids), 1)

        invoice = order.invoice_ids[0]
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(invoice.invoice_line_ids[0].quantity, 10.0)
        self.assertEqual(invoice.amount_total, 1000.0)
        self.assertEqual(result['res_model'], 'account.move')
        self.assertEqual(result['res_id'], invoice.id)

    def test_02_duplicate_invoice_raises_error(self):
        """Cannot force invoice if invoice already exists."""
        order = self._create_sale_order()
        wizard = self.env['sale.force.invoice.wizard'].create({
            'sale_order_id': order.id,
            'reason': 'customer_request',
        })
        wizard.action_confirm()

        wizard2 = self.env['sale.force.invoice.wizard'].create({
            'sale_order_id': order.id,
            'reason': 'customer_request',
        })
        with self.assertRaises(UserError):
            wizard2.action_confirm()

    def test_03_draft_order_raises_error(self):
        """Cannot force invoice a draft quotation."""
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'partner_invoice_id': self.partner.id,
            'partner_shipping_id': self.partner.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product.id,
                    'product_uom_qty': 5.0,
                    'price_unit': 100.0,
                }),
            ],
        })
        self.assertEqual(order.state, 'draft')
        with self.assertRaises(UserError):
            order.action_force_create_invoice('customer_request')

    def test_04_ordered_qty_used_regardless_of_policy(self):
        """Invoice qty equals ordered qty even with delivery policy."""
        self.assertEqual(self.product.invoice_policy, 'delivery')
        order = self._create_sale_order(qty=7, price=200.0)
        wizard = self.env['sale.force.invoice.wizard'].create({
            'sale_order_id': order.id,
            'reason': 'bill_exchange',
        })
        wizard.action_confirm()
        invoice = order.invoice_ids[0]
        self.assertEqual(invoice.invoice_line_ids[0].quantity, 7.0)
        self.assertEqual(invoice.amount_total, 1400.0)

    def test_05_chatter_message_logged(self):
        """Force invoice posts chatter message with details."""
        order = self._create_sale_order()
        wizard = self.env['sale.force.invoice.wizard'].create({
            'sale_order_id': order.id,
            'reason': 'bill_exchange',
        })
        wizard.action_confirm()
        self.assertTrue(
            any('Force Invoice created' in msg.body for msg in order.message_ids),
            "Chatter should contain force invoice message",
        )

    def test_06_security_normal_user_no_access(self):
        """Normal users cannot access force invoice wizard."""
        normal_user = self.env['res.users'].create({
            'name': 'Normal User',
            'login': 'normal_tester',
            'groups_id': [
                (4, self.env.ref('base.group_user').id),
            ],
        })
        self.assertFalse(
            normal_user.has_group(
                'buz_sale_force_invoice.group_force_invoice_manager',
            ),
        )
        with self.assertRaises(AccessError):
            self.env['sale.force.invoice.wizard'].with_user(normal_user).create({
                'sale_order_id': 1,
                'reason': 'customer_request',
            })
