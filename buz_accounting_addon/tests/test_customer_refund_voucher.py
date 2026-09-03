# -*- coding: utf-8 -*-
from odoo.tests import common, tagged
from odoo.exceptions import UserError, ValidationError, AccessError
from odoo import fields
import uuid

@tagged('post_install', '-at_install')
class TestCustomerRefundVoucher(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        # Journals
        self.bank_journal = self.env['account.journal'].search([('type','=','bank'),('company_id','=',self.company.id)], limit=1)
        if not self.bank_journal:
            self.bank_journal = self.env['account.journal'].create({
                'name': 'Test Bank ' + uuid.uuid4().hex[:4],
                'type': 'bank',
                'code': 'TBK' + uuid.uuid4().hex[:3].upper(),
                'company_id': self.company.id,
            })
        self.cash_journal = self.env['account.journal'].search([('type','=','cash'),('company_id','=',self.company.id)], limit=1)
        if not self.cash_journal:
            self.cash_journal = self.env['account.journal'].create({
                'name': 'Test Cash ' + uuid.uuid4().hex[:4],
                'type': 'cash',
                'code': 'TCS' + uuid.uuid4().hex[:3].upper(),
                'company_id': self.company.id,
            })
        # Customer
        self.customer = self.env['res.partner'].create({'name': 'CV Customer', 'customer_rank': 1, 'company_id': self.company.id})
        # Income account for writeoff
        self.writeoff_account = self.env['account.account'].search([('account_type','in',('income','income_other')),('company_id','=',self.company.id)], limit=1)
        if not self.writeoff_account:
            self.writeoff_account = self.env['account.account'].create({
                'name': 'WriteOff Income',
                'code': '41000' + uuid.uuid4().hex[:2],
                'account_type': 'income',
                'company_id': self.company.id,
            })
        # Create credit note 980
        self.credit_note = self._create_credit_note(980)

    def _create_credit_note(self, amount):
        # Use account.move with out_refund
        move = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0,0,{'name':'Refund','quantity':1,'price_unit': amount})],
        })
        move.action_post()
        return move

    def test_full_refund_cash(self):
        cn = self.credit_note
        cv = self.env['buz.customer.refund.voucher'].create({
            'credit_note_id': cn.id,
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'refund_amount': 980,
            'payment_type': 'cash',
            'destination_journal_id': self.cash_journal.id,
            'difference_handling': 'keep_open',
            'planned_payment_date': fields.Date.today(),
        })
        self.assertEqual(cv.state, 'draft')
        self.assertTrue(cv.name.startswith('CV/'))
        # Confirm
        cv.action_confirm()
        self.assertEqual(cv.state, 'confirmed')
        self.assertEqual(cv.workflow_state, 'confirmed')
        # Register via wrapper
        wiz = self.env['buz.customer.refund.payment.wizard'].create({'voucher_id': cv.id, 'payment_date': fields.Date.today()})
        wiz.action_create_payment()
        self.assertTrue(cv.payment_ids)
        pay = cv.payment_ids[0]
        self.assertEqual(pay.payment_type, 'outbound')
        self.assertEqual(pay.partner_type, 'customer')
        # For cash, should be paid or partially depending on reconciliation; with full refund CN should be 0
        cn.invalidate_recordset()
        self.assertAlmostEqual(abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') else cn.amount_residual, 0, places=2)

    def test_partial_keep_open(self):
        cn = self._create_credit_note(980)
        cv = self.env['buz.customer.refund.voucher'].create({
            'credit_note_id': cn.id,
            'refund_amount': 700,
            'payment_type': 'transfer',
            'destination_journal_id': self.bank_journal.id,
            'difference_handling': 'keep_open',
            'planned_payment_date': fields.Date.today(),
        })
        method = self.bank_journal.outbound_payment_method_line_ids[:1]
        if method:
            cv.payment_method_line_id = method.id
        cv.action_confirm()
        wiz = self.env['buz.customer.refund.payment.wizard'].create({'voucher_id': cv.id, 'payment_date': fields.Date.today()})
        wiz.action_create_payment()
        cn.invalidate_recordset()
        residual = abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') else cn.amount_residual
        self.assertAlmostEqual(residual, 280, places=1)
        # workflow partially_refunded or in_payment (if bank not reconciled)
        self.assertIn(cv.workflow_state, ('partially_refunded','in_payment','paid'))
        # create second CV from residual
        cv2 = self.env['buz.customer.refund.voucher'].create({
            'credit_note_id': cn.id,
            'refund_amount': 280,
            'payment_type': 'cash',
            'destination_journal_id': self.cash_journal.id,
            'difference_handling': 'keep_open',
        })
        cv2.action_confirm()
        # should be able to create because previous is not active terminal? For keep_open previous is partially_refunded (terminal)
        self.assertEqual(cv2.refund_amount, 280)

    def test_writeoff(self):
        cn = self._create_credit_note(980)
        cv = self.env['buz.customer.refund.voucher'].create({
            'credit_note_id': cn.id,
            'refund_amount': 700,
            'payment_type': 'transfer',
            'destination_journal_id': self.bank_journal.id,
            'difference_handling': 'writeoff',
            'writeoff_account_id': self.writeoff_account.id,
            'writeoff_reason': 'Discount',
        })
        method = self.bank_journal.outbound_payment_method_line_ids[:1]
        if method:
            cv.payment_method_line_id = method.id
        cv.action_confirm()
        wiz = self.env['buz.customer.refund.payment.wizard'].create({'voucher_id': cv.id, 'payment_date': fields.Date.today()})
        wiz.action_create_payment()
        cn.invalidate_recordset()
        residual = abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') else cn.amount_residual
        self.assertAlmostEqual(residual, 0, places=1)

    def test_deprecated_writeoff_account_is_rejected(self):
        deprecated_account = self.env['account.account'].create({
            'name': 'Deprecated WriteOff Income',
            'code': '41999' + uuid.uuid4().hex[:2],
            'account_type': 'income',
            'company_id': self.company.id,
            'deprecated': True,
        })

        with self.assertRaises(ValidationError):
            self.env['buz.customer.refund.voucher'].create({
                'credit_note_id': self.credit_note.id,
                'refund_amount': 700,
                'payment_type': 'transfer',
                'destination_journal_id': self.bank_journal.id,
                'difference_handling': 'writeoff',
                'writeoff_account_id': deprecated_account.id,
                'writeoff_reason': 'Regression test',
            })

    def test_available_writeoff_account_is_accepted(self):
        cv = self.env['buz.customer.refund.voucher'].create({
            'credit_note_id': self.credit_note.id,
            'refund_amount': 700,
            'payment_type': 'transfer',
            'destination_journal_id': self.bank_journal.id,
            'difference_handling': 'writeoff',
            'writeoff_account_id': self.writeoff_account.id,
            'writeoff_reason': 'Regression test',
        })

        self.assertEqual(cv.writeoff_account_id, self.writeoff_account)

    def test_validation_zero_and_exceed(self):
        cn = self._create_credit_note(500)
        with self.assertRaises(ValidationError):
            self.env['buz.customer.refund.voucher'].create({'credit_note_id': cn.id, 'refund_amount': 0, 'payment_type':'cash', 'destination_journal_id': self.cash_journal.id})
        with self.assertRaises(ValidationError):
            self.env['buz.customer.refund.voucher'].create({'credit_note_id': cn.id, 'refund_amount': 600, 'payment_type':'cash', 'destination_journal_id': self.cash_journal.id})
        # writeoff without account
        with self.assertRaises(ValidationError):
            cv = self.env['buz.customer.refund.voucher'].create({'credit_note_id': cn.id, 'refund_amount': 400, 'payment_type':'cash', 'destination_journal_id': self.cash_journal.id, 'difference_handling':'writeoff', 'writeoff_reason':'test'})
            cv.action_confirm()

    def test_sequence_and_name_edit(self):
        cn = self._create_credit_note(100)
        cv = self.env['buz.customer.refund.voucher'].create({'credit_note_id': cn.id, 'refund_amount': 100, 'payment_type':'cash', 'destination_journal_id': self.cash_journal.id})
        self.assertRegex(cv.name, r'^CV/\d{4}/\d{4}$')
        # Manager can edit in draft
        cv.with_user(self.env.ref('base.user_admin')).write({'name': f"CV/{fields.Date.today().year}/9999"})
        self.assertEqual(cv.name, f"CV/{fields.Date.today().year}/9999")
        # Duplicate should fail
        cn2 = self._create_credit_note(100)
        with self.assertRaises(ValidationError):
            cv2 = self.env['buz.customer.refund.voucher'].create({'credit_note_id': cn2.id, 'refund_amount': 100, 'payment_type':'cash', 'destination_journal_id': self.cash_journal.id})
            cv2.with_user(self.env.ref('base.user_admin')).write({'name': f"CV/{fields.Date.today().year}/9999"})

    def test_active_uniqueness(self):
        cn = self._create_credit_note(300)
        cv1 = self.env['buz.customer.refund.voucher'].create({'credit_note_id': cn.id, 'refund_amount': 100, 'payment_type':'cash', 'destination_journal_id': self.cash_journal.id})
        with self.assertRaises(ValidationError):
            self.env['buz.customer.refund.voucher'].create({'credit_note_id': cn.id, 'refund_amount': 100, 'payment_type':'cash', 'destination_journal_id': self.cash_journal.id})

    def test_wrapper_only_payment_date_editable(self):
        cn = self._create_credit_note(200)
        cv = self.env['buz.customer.refund.voucher'].create({'credit_note_id': cn.id, 'refund_amount': 200, 'payment_type':'transfer', 'destination_journal_id': self.bank_journal.id})
        cv.action_confirm()
        # try to bypass via direct payment.register with tampered amount - should be forced to cv amount
        ctx = {'active_model': 'account.move', 'active_ids': cn.ids, 'buz_customer_refund_voucher_id': cv.id}
        wiz = self.env['account.payment.register'].with_context(**ctx).create({'payment_date': fields.Date.today(), 'amount': 1, 'journal_id': self.bank_journal.id})
        # amount should be overridden to 200 via _compute and _create_payments guard
        # We check that validation will reset amount
        self.assertEqual(wiz.amount, 200)

    def test_unlink_prohibited(self):
        cv = self.env['buz.customer.refund.voucher'].create({'credit_note_id': self.credit_note.id, 'refund_amount': 100, 'payment_type':'cash', 'destination_journal_id': self.cash_journal.id})
        with self.assertRaises(UserError):
            cv.unlink()

    def test_print_validation(self):
        cn = self._create_credit_note(150)
        cv = self.env['buz.customer.refund.voucher'].create({'credit_note_id': cn.id, 'refund_amount': 150, 'payment_type':'cash', 'destination_journal_id': self.cash_journal.id})
        with self.assertRaises(UserError):
            cv.action_print()
        cv.action_confirm()
        # after confirm should allow
        cv.action_print()
        self.assertTrue(cv.printed_at)

    def test_multi_company(self):
        # create second company
        comp2 = self.env['res.company'].create({'name': 'Comp2 ' + uuid.uuid4().hex[:4]})
        # create customer for comp2? use same but check rule - CV for comp2 should not be visible from comp1
        # Simplified: ensure CV respects company field
        cn = self._create_credit_note(120)
        cv = self.env['buz.customer.refund.voucher'].create({'credit_note_id': cn.id, 'refund_amount': 120, 'company_id': self.company.id, 'payment_type':'cash', 'destination_journal_id': self.cash_journal.id})
        self.assertEqual(cv.company_id, self.company)

    def test_vendor_pv_not_affected(self):
        # Ensure vendor PV still works when CV not in context
        vendor = self.env['res.partner'].create({'name':'Vendor','supplier_rank':1})
        pv = self.env['account.payment.voucher'].create({'partner_id': vendor.id, 'date': fields.Date.today(), 'destination_journal_id': self.bank_journal.id})
        self.assertEqual(pv.state, 'draft')
