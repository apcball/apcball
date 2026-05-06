# -*- coding: utf-8 -*-
from unittest.mock import Mock

from odoo import fields
from odoo.tests.common import TransactionCase

from ..models.purchase_requisition import EmployeePurchaseRequisitionMonthly


class TestPurchaseRequisitionMonthlyBudget(TransactionCase):

    def test_expected_payment_without_vendor_uses_request_date_plus_30_days(self):
        req = self.env['employee.purchase.requisition'].new({
            'request_date': fields.Date.to_date('2026-04-12'),
        })

        req._compute_payment_date()

        self.assertEqual(
            req.payment_date,
            fields.Date.to_date('2026-05-12'),
        )

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
                'value': 'balance',
                'days': 15,
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

        self.assertEqual(
            req.payment_date,
            fields.Date.to_date('2026-04-27'),
        )
