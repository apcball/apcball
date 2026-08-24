# -*- coding: utf-8 -*-
from datetime import date

from .test_exchange_rate import ExchangeRateReceiptCase


class TestPartialReceipt(ExchangeRateReceiptCase):

    def test_partial_receipts_use_their_own_rate(self):
        """PO 100 pcs @ 10 USD. Receipt 1: 40 pcs @ 32.50. Receipt 2: 60 pcs @ 33.20."""
        po = self._create_po(self.usd, 10.0, 100, date(2026, 8, 1))
        picking1 = po.picking_ids
        move = picking1.move_ids
        move.quantity = 40
        move.picked = True
        picking1.exchange_rate_date = date(2026, 8, 15)
        picking1.exchange_rate = 32.50
        picking1.exchange_rate_source = 'manual'
        picking1.with_context(skip_backorder=True).button_validate()
        backorder = self.env['stock.picking'].search([
            ('backorder_id', '=', picking1.id),
        ], limit=1)
        self.assertTrue(backorder, "Backorder should be created for the remaining 60 pcs")

        svl1 = picking1.move_ids.stock_valuation_layer_ids
        self.assertAlmostEqual(sum(svl1.mapped('value')), 40 * 10 * 32.50, places=2)

        backorder.exchange_rate_date = date(2026, 8, 15)
        backorder.exchange_rate = 33.20
        backorder.exchange_rate_source = 'manual'
        for bmove in backorder.move_ids:
            bmove.quantity = 60
            bmove.picked = True
        backorder.button_validate()

        svl2 = backorder.move_ids.stock_valuation_layer_ids
        self.assertAlmostEqual(sum(svl2.mapped('value')), 60 * 10 * 33.20, places=2)
