from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.sale.tests.common import SaleCommon


@tagged('post_install', '-at_install')
class TestCancelLock(SaleCommon):

    def _confirmed_order(self):
        order = self.empty_order.copy({'order_line': [(0, 0, {
            'product_id': self.product.id, 'product_uom_qty': 1,
        })]})
        order.action_confirm()
        return order

    def _invoice(self, order, post=True):
        order.order_line.qty_delivered = 1
        invoice = order._create_invoices()
        if post:
            invoice.action_post()
        return invoice

    def test_posted_invoice_blocks(self):
        order = self._confirmed_order()
        self._invoice(order)
        with self.assertRaises(UserError):
            order._action_cancel()
        self.assertEqual(order.state, 'sale')

    def test_draft_invoice_allows(self):
        order = self._confirmed_order()
        invoice = self._invoice(order, post=False)
        order._action_cancel()
        self.assertEqual(order.state, 'cancel')
        self.assertEqual(invoice.state, 'cancel')

    def test_reversed_invoice_blocks(self):
        order = self._confirmed_order()
        invoice = self._invoice(order)
        wizard = self.env['account.move.reversal'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({'journal_id': invoice.journal_id.id})
        wizard.refund_moves()
        with self.assertRaises(UserError):
            order._action_cancel()

    def test_reset_cancelled_invoice_allows(self):
        order = self._confirmed_order()
        invoice = self._invoice(order)
        invoice.button_draft()
        invoice.button_cancel()
        order._action_cancel()
        self.assertEqual(order.state, 'cancel')

    def test_batch_all_or_nothing(self):
        locked = self._confirmed_order()
        self._invoice(locked)
        free = self._confirmed_order()
        with self.assertRaises(UserError):
            (locked | free)._action_cancel()
        self.assertEqual(free.state, 'sale')

    def test_action_cancel_blocked(self):
        order = self._confirmed_order()
        self._invoice(order)
        with self.assertRaises(UserError):
            order.with_context(disable_cancel_warning=True).action_cancel()
