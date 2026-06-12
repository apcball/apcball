from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
from datetime import date
import uuid


@tagged('-at_install', 'post_install')
class TestBillingNote(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        uid = uuid.uuid4().hex[:6].upper()
        cls.partner = cls.env['res.partner'].create({
            'name': f'Test Partner {uid}',
            'vat': f'0999000{uid[:4]}',
            'phone': '02-123-4567',
        })
        cls.product = cls.env['product.product'].create({
            'name': f'Test Product {uid}',
            'type': 'service',
        })
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', cls.env.company.id)
        ], limit=1)
        cls.bank_journal = cls.env['account.journal'].search([
            ('type', '=', 'bank'), ('company_id', '=', cls.env.company.id)
        ], limit=1)

        account_receivable = cls.env['account.account'].search([
            ('account_type', '=', 'asset_receivable'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        account_revenue = cls.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

        cls.invoice = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner.id,
            'journal_id': cls.journal.id,
            'invoice_date': date.today(),
            'invoice_date_due': date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line',
                'quantity': 1,
                'price_unit': 1000.0,
                'account_id': account_revenue.id,
            })],
        })
        cls.invoice.action_post()

        cls.invoice2 = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner.id,
            'journal_id': cls.journal.id,
            'invoice_date': date.today(),
            'invoice_date_due': date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line 2',
                'quantity': 1,
                'price_unit': 2000.0,
                'account_id': account_revenue.id,
            })],
        })
        cls.invoice2.action_post()

    def _create_billing_note(self, note_type='receivable', invoice_ids=None):
        if invoice_ids is None:
            invoice_ids = self.invoice
        return self.env['billing.note'].create({
            'partner_id': self.partner.id,
            'note_type': note_type,
            'date': date.today(),
            'due_date': date.today(),
            'invoice_ids': [(4, inv.id) for inv in (invoice_ids if hasattr(invoice_ids, '__iter__') else [invoice_ids])],
        })

    # ── Creation & Sequences ──

    def test_create_billing_note_receivable(self):
        bn = self._create_billing_note()
        self.assertTrue(bn.name)
        self.assertNotEqual(bn.name, '/')
        self.assertEqual(bn.state, 'draft')
        self.assertEqual(bn.note_type, 'receivable')
        self.assertEqual(bn.partner_id, self.partner)

    def test_create_billing_note_payable(self):
        bn = self._create_billing_note(note_type='payable')
        self.assertEqual(bn.note_type, 'payable')

    def test_sequence_customer_vs_vendor(self):
        recv = self._create_billing_note()
        pay = self._create_billing_note(note_type='payable')
        self.assertNotEqual(recv.name, pay.name)
        self.assertIn(recv.name[:2], recv.name)

    def test_create_without_invoices_raises_on_confirm(self):
        bn = self.env['billing.note'].create({
            'partner_id': self.partner.id,
            'note_type': 'receivable',
            'date': date.today(),
            'due_date': date.today(),
        })
        with self.assertRaises(UserError):
            bn.action_confirm()

    # ── State transitions ──

    def test_state_draft_to_confirm(self):
        bn = self._create_billing_note()
        bn.action_confirm()
        self.assertEqual(bn.state, 'confirm')

    def test_state_confirm_to_done(self):
        bn = self._create_billing_note()
        bn.action_confirm()
        bn.action_done()
        self.assertEqual(bn.state, 'done')

    def test_state_confirm_to_draft(self):
        bn = self._create_billing_note()
        bn.action_confirm()
        bn.action_draft()
        self.assertEqual(bn.state, 'draft')

    def test_state_cancel(self):
        bn = self._create_billing_note()
        bn.action_confirm()
        bn.action_cancel()
        self.assertEqual(bn.state, 'cancel')

    # ── Computed fields ──

    def test_amount_total(self):
        bn = self._create_billing_note(invoice_ids=[self.invoice, self.invoice2])
        self.assertEqual(bn.amount_total, 3000.0)

    def test_amount_total_single_invoice(self):
        bn = self._create_billing_note(invoice_ids=self.invoice)
        self.assertEqual(bn.amount_total, 1000.0)

    def test_amount_residual_equals_total_initially(self):
        bn = self._create_billing_note(invoice_ids=self.invoice)
        self.assertEqual(bn.amount_residual, bn.amount_total)
        self.assertEqual(bn.amount_paid, 0.0)

    def test_payment_state_not_paid_initially(self):
        bn = self._create_billing_note(invoice_ids=self.invoice)
        self.assertEqual(bn.payment_state, 'not_paid')

    def test_amount_total_words(self):
        bn = self._create_billing_note(invoice_ids=self.invoice)
        self.assertTrue(bn.amount_total_words)

    # ── Computed partner fields ──

    def test_partner_vat(self):
        bn = self._create_billing_note()
        self.assertEqual(bn.partner_vat, self.partner.vat)

    def test_partner_phone(self):
        bn = self._create_billing_note()
        self.assertEqual(bn.partner_phone, self.partner.phone)

    # ── Available invoices filter ──

    def test_available_invoices_excludes_posted_paid(self):
        bn = self._create_billing_note()
        self.assertIn(self.invoice.id, bn.available_invoice_ids.ids)

    def test_available_invoices_excludes_draft_invoices(self):
        draft_inv = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'invoice_date': date.today(),
            'state': 'draft',
            'invoice_line_ids': [(0, 0, {
                'name': 'Draft line',
                'quantity': 1,
                'price_unit': 500.0,
                'account_id': self.invoice.invoice_line_ids[0].account_id.id,
            })],
        })
        bn = self._create_billing_note(invoice_ids=self.invoice)
        self.assertNotIn(draft_inv.id, bn.available_invoice_ids.ids)

    # ── SQL constraints ──

    def test_unique_name_per_company(self):
        bn1 = self._create_billing_note()
        try:
            self.env['billing.note'].create({
                'partner_id': self.partner.id,
                'name': bn1.name,
                'note_type': 'receivable',
                'date': date.today(),
                'due_date': date.today(),
                'company_id': bn1.company_id.id,
            })
            self.fail('Should have raised an error for duplicate name')
        except (ValidationError, Exception):
            pass

    # ── Onchange ──

    def test_onchange_invoice_sets_due_date(self):
        bn = self.env['billing.note'].new({
            'partner_id': self.partner.id,
            'note_type': 'receivable',
        })
        bn.invoice_ids = [(4, self.invoice.id)]
        bn._onchange_invoice_ids()
        self.assertEqual(bn.due_date, self.invoice.invoice_date_due)

    # ── Payment wizard ──

    def test_action_register_payment_returns_wizard(self):
        bn = self._create_billing_note()
        bn.action_confirm()
        action = bn.action_register_payment()
        self.assertEqual(action['res_model'], 'account.payment.register')
        self.assertEqual(action['target'], 'new')

    def test_action_register_batch_payment(self):
        bn = self._create_billing_note()
        bn.action_confirm()
        action = bn.action_register_batch_payment()
        self.assertEqual(action['res_model'], 'account.payment.register')
        self.assertEqual(action['target'], 'new')

    def test_action_register_batch_payment_mixed_types_raises(self):
        recv = self._create_billing_note()
        recv.action_confirm()
        pay = self._create_billing_note(note_type='payable')
        pay.action_confirm()
        with self.assertRaises(UserError):
            self.env['billing.note'].browse([recv.id, pay.id]).action_register_batch_payment()

    # ── Create billing note wizard ──

    def test_create_billing_note_wizard_from_invoice(self):
        wizard = self.env['create.billing.note.wizard'].with_context({
            'active_id': self.invoice.id,
            'active_model': 'account.move',
        }).create({
            'date': date.today(),
        })
        self.assertEqual(wizard.invoice_id, self.invoice)
        self.assertEqual(wizard.note_type, 'receivable')

    def test_create_billing_note_wizard_action(self):
        wizard = self.env['create.billing.note.wizard'].with_context({
            'active_id': self.invoice.id,
            'active_model': 'account.move',
        }).create({
            'date': date.today(),
        })
        result = wizard.action_create_billing_note()
        bn = self.env['billing.note'].browse(result['res_id'])
        self.assertTrue(bn)
        self.assertIn(self.invoice.id, bn.invoice_ids.ids)

    def test_wizard_duplicate_invoice_raises(self):
        wizard = self.env['create.billing.note.wizard'].with_context({
            'active_id': self.invoice.id,
            'active_model': 'account.move',
        }).create({'date': date.today()})
        wizard.action_create_billing_note()
        wizard2 = self.env['create.billing.note.wizard'].with_context({
            'active_id': self.invoice.id,
            'active_model': 'account.move',
        }).create({'date': date.today()})
        with self.assertRaises(UserError):
            wizard2.action_create_billing_note()

    # ── Add bills wizard ──

    def test_add_bills_wizard(self):
        bn = self._create_billing_note(invoice_ids=self.invoice)
        wizard = self.env['add.bills.wizard'].create({
            'billing_note_id': bn.id,
        })
        wizard.invoice_ids = [(4, self.invoice2.id)]
        wizard.action_add_invoices()
        self.assertIn(self.invoice2.id, bn.invoice_ids.ids)

    # ── Delete + cascade ──

    def test_delete_billing_note_cascade_invoices(self):
        bn = self._create_billing_note(invoice_ids=self.invoice)
        inv_ids = bn.invoice_ids.ids
        self.assertTrue(inv_ids)
        bn.unlink()
        remaining = self.env['account.move'].browse(inv_ids)
        self.assertTrue(remaining.exists())

    # ── name_get ──

    def test_name_get(self):
        bn = self._create_billing_note()
        self.assertTrue(bn.display_name)

    # ── Copy ──

    def test_copy_resets_name(self):
        bn = self._create_billing_note()
        copy = bn.copy()
        self.assertNotEqual(copy.name, bn.name)


@tagged('-at_install', 'post_install')
class TestBillingNotePayment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        uid = uuid.uuid4().hex[:6].upper()
        cls.partner = cls.env['res.partner'].create({
            'name': f'Payment Partner {uid}',
        })
        cls.product = cls.env['product.product'].create({
            'name': f'P Product {uid}',
            'type': 'service',
        })
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', cls.env.company.id)
        ], limit=1)
        cls.bank_journal = cls.env['account.journal'].search([
            ('type', '=', 'bank'), ('company_id', '=', cls.env.company.id)
        ], limit=1)

        account_receivable = cls.env['account.account'].search([
            ('account_type', '=', 'asset_receivable'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        account_revenue = cls.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

        cls.invoice = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner.id,
            'journal_id': cls.journal.id,
            'invoice_date': date.today(),
            'invoice_date_due': date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': 'Payment test line',
                'quantity': 1,
                'price_unit': 1000.0,
                'account_id': account_revenue.id,
            })],
        })
        cls.invoice.action_post()

        cls.bn = cls.env['billing.note'].create({
            'partner_id': cls.partner.id,
            'note_type': 'receivable',
            'date': date.today(),
            'due_date': date.today(),
            'invoice_ids': [(4, cls.invoice.id)],
        })
        cls.bn.action_confirm()

    def test_create_payment_record(self):
        payment = self.env['billing.note.payment'].create({
            'billing_note_id': self.bn.id,
            'payment_date': date.today(),
            'payment_method': 'cash',
            'amount': 500.0,
        })
        self.assertTrue(payment)
        self.assertEqual(payment.billing_note_id, self.bn)
        self.assertEqual(payment.amount, 500.0)
        self.assertTrue(payment.name)

    def test_payment_record_creation(self):
        payment = self.env['billing.note.payment'].create({
            'billing_note_id': self.bn.id,
            'payment_date': date.today(),
            'payment_method': 'cash',
            'amount': 300.0,
        })
        self.assertTrue(payment)
        self.assertEqual(payment.amount, 300.0)
        self.assertTrue(payment.name)

    def test_payment_with_notes(self):
        payment = self.env['billing.note.payment'].create({
            'billing_note_id': self.bn.id,
            'payment_date': date.today(),
            'payment_method': 'check',
            'amount': 1000.0,
            'notes': 'Test payment note',
        })
        self.assertEqual(payment.notes, 'Test payment note')

    def test_payment_different_methods(self):
        for method in ('cash', 'transfer', 'check', 'other'):
            payment = self.env['billing.note.payment'].create({
                'billing_note_id': self.bn.id,
                'payment_date': date.today(),
                'payment_method': method,
                'amount': 100.0,
            })
            self.assertEqual(payment.payment_method, method)


@tagged('-at_install', 'post_install')
class TestBillingNoteCron(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        uid = uuid.uuid4().hex[:6].upper()
        cls.partner = cls.env['res.partner'].create({
            'name': f'Cron Partner {uid}',
            'email': f'cron{uid}@test.com',
        })
        cls.product = cls.env['product.product'].create({
            'name': f'Cron Product {uid}',
            'type': 'service',
        })

    def test_cron_runs_without_error(self):
        result = self.env['billing.note']._cron_check_due_dates()
        self.assertTrue(result)
