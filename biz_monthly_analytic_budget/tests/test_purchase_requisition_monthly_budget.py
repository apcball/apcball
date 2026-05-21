# -*- coding: utf-8 -*-
from unittest.mock import Mock

from odoo import fields
from odoo.tests.common import TransactionCase

from odoo.addons.biz_monthly_analytic_budget.models.purchase_requisition import EmployeePurchaseRequisitionMonthly


class TestPurchaseRequisitionMonthlyBudget(TransactionCase):

    def test_expected_payment_without_vendor_uses_request_date_plus_30_days(self):
        req = self.env['employee.purchase.requisition'].new({
            'request_date': fields.Date.to_date('2026-04-12'),
        })
        req._compute_payment_date()
        self.assertEqual(req.payment_date, fields.Date.to_date('2026-05-12'))

    def test_request_open_date_falls_back_to_create_date_when_request_date_missing(self):
        fake = Mock(
            request_date=False,
            create_date=fields.Datetime.to_datetime('2026-04-12 08:30:00'),
        )
        self.assertEqual(
            EmployeePurchaseRequisitionMonthly._get_request_open_date(fake),
            fields.Date.to_date('2026-04-12'),
        )

    def test_expected_payment_with_vendor_uses_payment_term(self):
        payment_term = self.env['account.payment.term'].create({
            'name': 'Net 15',
            'line_ids': [(0, 0, {
                'value': 'percent',
                'value_amount': 100.0,
                'nb_days': 15,
                'delay_type': 'days_after',
            })],
        })
        vendor = self.env['res.partner'].create({
            'name': 'Vendor A',
            'property_supplier_payment_term_id': payment_term.id,
        })
        req = self.env['employee.purchase.requisition'].new({
            'request_date': fields.Date.to_date('2026-04-12'),
            'vendor_id': vendor.id,
        })
        req._compute_payment_date()
        self.assertEqual(req.payment_date, fields.Date.to_date('2026-04-27'))

    def test_onchange_vendor_updates_expected_payment_from_default_to_payment_term(self):
        payment_term = self.env['account.payment.term'].create({
            'name': 'Net 60',
            'line_ids': [(0, 0, {
                'value': 'percent',
                'value_amount': 100.0,
                'nb_days': 60,
                'delay_type': 'days_after',
            })],
        })
        vendor = self.env['res.partner'].create({
            'name': 'Vendor B',
            'property_supplier_payment_term_id': payment_term.id,
        })
        req = self.env['employee.purchase.requisition'].new({
            'request_date': fields.Date.to_date('2026-04-12'),
        })
        req._compute_payment_date()
        self.assertEqual(req.payment_date, fields.Date.to_date('2026-05-12'))

        req.vendor_id = vendor
        req._onchange_payment_date_inputs()
        self.assertEqual(req.payment_date, fields.Date.to_date('2026-06-11'))

    def test_expected_payment_uses_single_line_vendor_payment_term(self):
        payment_term = self.env['account.payment.term'].create({
            'name': 'Net 60',
            'line_ids': [(0, 0, {
                'value': 'percent',
                'value_amount': 100.0,
                'nb_days': 60,
                'delay_type': 'days_after',
            })],
        })
        vendor = self.env['res.partner'].create({
            'name': 'Vendor Line',
            'property_supplier_payment_term_id': payment_term.id,
        })
        product = self.env['product.product'].create({
            'name': 'Test Product',
        })
        req = self.env['employee.purchase.requisition'].new({
            'request_date': fields.Date.to_date('2026-04-12'),
            'requisition_order_ids': [(0, 0, {
                'product_id': product.id,
                'quantity': 1.0,
                'partner_id': vendor.id,
            })],
        })
        req._compute_payment_date()
        self.assertEqual(req.payment_date, fields.Date.to_date('2026-06-11'))

    def test_auto_expected_payment_does_not_create_manual_override(self):
        req = self.env['employee.purchase.requisition'].new({
            'request_date': fields.Date.to_date('2026-04-12'),
        })
        req._compute_payment_date()
        req._inverse_payment_date()
        self.assertFalse(req.payment_date_manual)

    def test_manual_expected_payment_is_preserved_as_override(self):
        req = self.env['employee.purchase.requisition'].new({
            'request_date': fields.Date.to_date('2026-04-12'),
        })
        req.payment_date = fields.Date.to_date('2026-05-20')
        req._inverse_payment_date()
        self.assertEqual(req.payment_date_manual, fields.Date.to_date('2026-05-20'))
