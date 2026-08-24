# -*- coding: utf-8 -*-
from datetime import date

from .test_exchange_rate import ExchangeRateReceiptCase


class TestReceiptValuation(ExchangeRateReceiptCase):

    def test_svl_matches_accounting_valuation(self):
        product = self.env['product.product'].search([
            ('type', '=', 'product'),
            ('categ_id.property_valuation', '=', 'real_time'),
            ('categ_id.property_cost_method', 'in', ('average', 'fifo')),
            ('company_id', 'in', (False, self.company.id)),
        ], limit=1)
        if not product:
            self.skipTest("No automated-valuation product available on this database.")
        self.product = product

        po = self._create_po(self.usd, 10.0, 10, date(2026, 8, 1))
        picking = po.picking_ids
        self._validate_receipt(
            picking, exchange_rate_date=date(2026, 8, 15),
            exchange_rate=32.85, source='manual',
        )
        svl = picking.move_ids.stock_valuation_layer_ids
        self.assertTrue(svl.account_move_id)
        journal_entry = svl.account_move_id
        self.assertEqual(journal_entry.state, 'posted')
        self.assertAlmostEqual(
            sum(journal_entry.line_ids.mapped('balance')), 0.0, places=2,
            msg="Journal entry must be balanced",
        )
        stock_valuation_lines = journal_entry.line_ids.filtered(
            lambda l: l.account_id == self.product.categ_id.property_stock_valuation_account_id
        )
        self.assertAlmostEqual(
            sum(stock_valuation_lines.mapped('balance')), svl.value, places=2,
            msg="Accounting valuation must reconcile with the SVL value",
        )
