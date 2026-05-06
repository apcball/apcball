# -*- coding: utf-8 -*-
from unittest.mock import Mock, patch

from odoo import fields
from odoo.tests.common import TransactionCase


class TestAccountMoveMonthlyBudget(TransactionCase):

    def test_bill_target_date_prefers_invoice_date_due_over_related_po_payment_date(self):
        bill = self.env['account.move'].new({
            'move_type': 'in_invoice',
            'invoice_date_due': fields.Date.to_date('2026-04-30'),
            'invoice_date': fields.Date.to_date('2026-04-20'),
            'date': fields.Date.to_date('2026-04-18'),
        })
        related_po = Mock(
            payment_date=fields.Date.to_date('2026-04-10'),
            date_order=False,
        )

        with patch.object(type(bill), '_get_related_purchase_order', return_value=related_po):
            self.assertEqual(
                bill._get_bill_target_date(),
                fields.Date.to_date('2026-04-30'),
            )

    def test_bill_target_date_falls_back_to_related_po_payment_date_when_due_date_missing(self):
        bill = self.env['account.move'].new({
            'move_type': 'in_invoice',
            'invoice_date': fields.Date.to_date('2026-04-20'),
            'date': fields.Date.to_date('2026-04-18'),
        })
        related_po = Mock(
            payment_date=fields.Date.to_date('2026-04-10'),
            date_order=False,
        )

        with patch.object(type(bill), '_get_related_purchase_order', return_value=related_po):
            self.assertEqual(
                bill._get_bill_target_date(),
                fields.Date.to_date('2026-04-10'),
            )

    def test_bill_target_date_falls_back_to_po_date_order(self):
        bill = self.env['account.move'].new({
            'move_type': 'in_invoice',
            'invoice_date': fields.Date.to_date('2026-04-20'),
            'date': fields.Date.to_date('2026-04-18'),
        })
        related_po = Mock(
            payment_date=False,
            date_order=fields.Datetime.to_datetime('2026-04-12 00:00:00'),
        )

        with patch.object(type(bill), '_get_related_purchase_order', return_value=related_po):
            self.assertEqual(
                bill._get_bill_target_date(),
                fields.Date.to_date('2026-04-12'),
            )

    def test_bill_target_date_returns_false_when_due_date_and_related_po_date_are_missing(self):
        bill = self.env['account.move'].new({
            'move_type': 'in_invoice',
            'invoice_date': fields.Date.to_date('2026-04-20'),
            'date': fields.Date.to_date('2026-04-18'),
        })
        related_po = Mock(payment_date=False, date_order=False)

        with patch.object(type(bill), '_get_related_purchase_order', return_value=related_po):
            self.assertFalse(bill._get_bill_target_date())

    def test_related_purchase_order_prefers_purchase_id_if_present(self):
        partner = self.env['res.partner'].create({'name': 'Test Vendor'})
        expected_po = self.env['purchase.order'].create({
            'partner_id': partner.id,
        })
        bill = self.env['account.move'].new({'move_type': 'in_invoice'})
        bill.purchase_id = expected_po

        with patch.object(type(bill), 'sudo', side_effect=AssertionError('sudo search fallback should not run')):
            self.assertIs(bill._get_related_purchase_order(), expected_po)

    def test_related_purchase_order_falls_back_to_invoice_origin_search(self):
        bill = self.env['account.move'].new({
            'move_type': 'in_invoice',
            'invoice_origin': 'PO00042',
        })
        expected_po = Mock(exists=lambda: True)
        purchase_model = self.env['purchase.order']

        with patch.object(type(purchase_model), 'sudo', return_value=purchase_model):
            with patch.object(type(purchase_model), 'search', return_value=expected_po):
                self.assertIs(bill._get_related_purchase_order(), expected_po)

    def test_sync_monthly_bill_budget_refreshes_auto_filled_due_date_when_po_changes(self):
        partner = self.env['res.partner'].create({'name': 'Vendor Y'})
        purchase_order = self.env['purchase.order'].create({
            'partner_id': partner.id,
        })
        purchase_order.write({'payment_date': fields.Date.to_date('2026-05-10')})

        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.env.company.id),
        ], limit=1) or self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id),
        ], limit=1)

        with patch.object(type(self.env['budget.engine']), 'release_budget', return_value=None):
            bill = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': partner.id,
                'journal_id': purchase_journal.id,
                'invoice_origin': purchase_order.name,
            })
            self.assertEqual(bill.invoice_date_due, fields.Date.to_date('2026-05-10'))
            self.assertTrue(bill.monthly_bill_due_date_from_po)

            purchase_order.write({'payment_date': fields.Date.to_date('2026-06-15')})

        bill.invalidate_recordset(['invoice_date_due', 'monthly_bill_due_date_from_po'])
        self.assertEqual(bill.invoice_date_due, fields.Date.to_date('2026-06-15'))
        self.assertTrue(bill.monthly_bill_due_date_from_po)

    def test_sync_monthly_bill_budget_keeps_manual_due_date_when_po_changes(self):
        partner = self.env['res.partner'].create({'name': 'Vendor Z'})
        purchase_order = self.env['purchase.order'].create({
            'partner_id': partner.id,
        })
        purchase_order.write({'payment_date': fields.Date.to_date('2026-05-10')})

        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.env.company.id),
        ], limit=1) or self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id),
        ], limit=1)

        with patch.object(type(self.env['budget.engine']), 'release_budget', return_value=None):
            bill = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': partner.id,
                'journal_id': purchase_journal.id,
                'invoice_origin': purchase_order.name,
                'invoice_date_due': fields.Date.to_date('2026-04-30'),
            })
            self.assertFalse(bill.monthly_bill_due_date_from_po)

            purchase_order.write({'payment_date': fields.Date.to_date('2026-06-15')})

        bill.invalidate_recordset(['invoice_date_due', 'monthly_bill_due_date_from_po'])
        self.assertEqual(bill.invoice_date_due, fields.Date.to_date('2026-04-30'))
        self.assertFalse(bill.monthly_bill_due_date_from_po)

    def test_unlink_po_linked_bill_does_not_touch_po_budget_context(self):
        partner = self.env['res.partner'].create({'name': 'Vendor Delete Bill'})
        purchase_order = self.env['purchase.order'].create({
            'partner_id': partner.id,
        })
        purchase_order.write({'payment_date': fields.Date.to_date('2026-05-10')})

        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.env.company.id),
        ], limit=1) or self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id),
        ], limit=1)

        release_calls = []

        def _capture_release(context):
            release_calls.append(context.copy())
            return None

        with patch.object(type(self.env['budget.engine']), 'release_budget', side_effect=_capture_release):
            bill = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': partner.id,
                'journal_id': purchase_journal.id,
                'invoice_origin': purchase_order.name,
            })
            release_calls.clear()
            bill.unlink()

        self.assertTrue(release_calls)
        self.assertTrue(all(call['document_model'] == 'account.move' for call in release_calls))
        self.assertTrue(all(call['document_id'] == bill.id for call in release_calls))
        self.assertTrue(all(call['budget_source'] == 'monthly' for call in release_calls))
