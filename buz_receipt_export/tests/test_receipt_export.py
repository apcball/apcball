# -*- coding: utf-8 -*-

from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestReceiptExportWizard(TransactionCase):
    """Unit coverage for the report wizard's deterministic logic."""

    def _wizard(self, **values):
        defaults = {
            'date_type': 'voucher_date',
            'date_from': date(2026, 1, 1),
            'date_to': date(2026, 12, 31),
            'status': 'posted',
            'amount_basis': 'amount_to_collect',
            'company_id': self.env.company.id,
        }
        defaults.update(values)
        return self.env['buz.receipt.export.wizard'].create(defaults)

    def test_date_range_validation(self):
        wizard = self._wizard(
            date_from=date(2026, 12, 31), date_to=date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError):
            wizard._validate_date_range(wizard.date_from, wizard.date_to)

    def test_amount_basis_labels_are_explicit(self):
        wizard = self._wizard(amount_basis='paid_to_date')
        self.assertEqual(wizard.amount_basis_label, 'Paid to Date')

    def test_no_matching_rows_is_rejected(self):
        wizard = self._wizard()
        with self.assertRaises(UserError):
            wizard.action_export_xlsx()
