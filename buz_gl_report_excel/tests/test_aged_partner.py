from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAgedPartner(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].with_context(
            skip_partner_required_fields=True).create({'name': 'Aged Test Partner'})
        cls.income = cls.env['account.account'].search([
            ('account_type', '=', 'income'), ('company_id', '=', cls.company.id)], limit=1)
        cls.today = fields.Date.today()

    def _move(self, move_type, amount, post=True):
        move = self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': self.partner.id,
            'invoice_date': self.today,
            'invoice_date_due': self.today,
            'invoice_line_ids': [fields.Command.create({
                'name': 'x', 'quantity': 1, 'price_unit': amount,
                'account_id': self.income.id, 'tax_ids': [fields.Command.clear()],
            })],
        })
        if post:
            move.action_post()
        return move

    def _run(self, **kw):
        form = {
            'date_as_of': self.today, 'company_id': self.company.id,
            'direction_selection': 'past', 'period_length': 30,
            'target_move': 'posted', 'partner_ids': [self.partner.id],
            'account_ids': [], 'journal_ids': [], 'result_selection': 'customer',
        }
        form.update(kw)
        self.env.flush_all()  # report reads via raw SQL
        res = self.env['report.buz_gl_report_excel.report_aged_partner']._get_report_values(
            [], data={'form': form})
        return sum(p['total'] for p in res['partners'])

    def test_cancelled_excluded_with_all_entries(self):
        self._move('out_invoice', 100)
        cancelled = self._move('out_invoice', 50)
        cancelled.button_draft()
        cancelled.button_cancel()
        self.assertEqual(cancelled.state, 'cancel')
        self.assertAlmostEqual(self._run(target_move='all'), 100.0)
        self.assertAlmostEqual(self._run(target_move='posted'), 100.0)

    def test_customer_supplier_sign_by_account_type(self):
        self._move('out_invoice', 100)
        self._move('out_refund', 30)  # receivable credit balance stays negative
        self._move('in_invoice', 40)  # payable shown positive
        self.assertAlmostEqual(self._run(result_selection='customer_supplier'), 100 - 30 + 40)

    def test_receivable_payable_wrappers(self):
        self._move('out_invoice', 100)
        self._move('in_invoice', 40)
        self.env.flush_all()
        form = {
            'date_as_of': self.today, 'company_id': self.company.id,
            'direction_selection': 'past', 'period_length': 30,
            'target_move': 'posted', 'partner_ids': [self.partner.id],
            'account_ids': [], 'journal_ids': [],
        }
        for kind, expected in (('receivable', 100.0), ('payable', 40.0)):
            res = self.env['report.buz_gl_report_excel.report_aged_%s' % kind]._get_report_values(
                [], data={'form': dict(form)})
            self.assertAlmostEqual(sum(p['total'] for p in res['partners']), expected)
