from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSettlementGuards(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Partner = cls.env['res.partner'].with_context(skip_partner_required_fields=True)
        cls.payer = Partner.create({'name': 'ARS Payer'})
        cls.customer = Partner.create({'name': 'ARS Customer'})
        cls.income = cls.env['account.account'].search([
            ('account_type', '=', 'income'), ('company_id', '=', cls.company.id)], limit=1)
        cls.bank = cls.env['account.journal'].search([
            ('type', '=', 'bank'), ('company_id', '=', cls.company.id)], limit=1)
        cls.today = fields.Date.today()

    def _invoice(self, amount=100.0):
        inv = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.customer.id,
            'invoice_date': self.today, 'invoice_date_due': self.today,
            'invoice_line_ids': [fields.Command.create({
                'name': 'x', 'quantity': 1, 'price_unit': amount,
                'account_id': self.income.id, 'tax_ids': [fields.Command.clear()],
            })],
        })
        inv.action_post()
        return inv

    def _settlement(self, invoice, amount=100.0):
        vals = {
            'partner_id': self.payer.id, 'journal_id': self.bank.id,
            'payment_date': self.today, 'amount_received': amount,
            'line_ids': [fields.Command.create({
                'invoice_id': invoice.id, 'pay_amount': amount, 'selected': True})],
        }
        if 'payment_channel' in self.env['ar.settlement']._fields:
            sel = self.env['ar.settlement']._fields['payment_channel'].selection
            if sel:
                vals['payment_channel'] = sel[0][0]
        return self.env['ar.settlement'].create(vals)

    def _clearings(self, settlement):
        return self.env['account.move'].search([('ar_settlement_id', '=', settlement.id)])

    def test_confirm_links_clearing_and_pays_invoice(self):
        inv = self._invoice()
        st = self._settlement(inv)
        st.action_confirm()
        self.assertEqual(len(self._clearings(st)), 1)
        self.assertEqual(inv.payment_state, 'paid')

    def test_stale_draft_cannot_create_duplicate_clearing(self):
        inv = self._invoice()
        first = self._settlement(inv)
        stale = self._settlement(inv)
        first.action_confirm()
        with self.assertRaises(UserError):
            stale.action_confirm()
        self.assertFalse(self._clearings(stale))
        self.assertEqual(stale.state, 'draft')

    def test_cancel_reverses_clearing_and_payment(self):
        inv = self._invoice()
        st = self._settlement(inv)
        st.action_confirm()
        payment = st.payment_id
        st.action_cancel()
        self.assertEqual(st.state, 'cancelled')
        self.assertEqual(payment.state, 'cancel')
        self.assertFalse(self.env['account.move'].search([
            ('ar_settlement_id', '=', st.id), ('state', '=', 'posted')]))
        self.assertNotEqual(inv.payment_state, 'paid')

    def test_unlink_blocked_when_live(self):
        inv = self._invoice()
        st = self._settlement(inv)
        st.action_confirm()
        with self.assertRaises(UserError):
            st.unlink()
        st.action_cancel()
        st.unlink()  # reversed -> deletable
