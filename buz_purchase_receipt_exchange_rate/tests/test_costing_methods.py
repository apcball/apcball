# -*- coding: utf-8 -*-
from datetime import date

from .test_exchange_rate import ExchangeRateReceiptCase


class TestCostingMethods(ExchangeRateReceiptCase):

    def _product_with_cost_method(self, method):
        product = self.env['product.product'].search([
            ('type', '=', 'product'),
            ('categ_id.property_cost_method', '=', method),
            ('company_id', 'in', (False, self.company.id)),
        ], limit=1)
        return product

    def test_avco_average_cost_updates_with_receipt_rate(self):
        product = self._product_with_cost_method('average')
        if not product:
            self.skipTest("No AVCO product available on this database.")
        self.product = product
        po = self._create_po(self.usd, 10.0, 10, date(2026, 8, 1))
        picking = po.picking_ids
        self._validate_receipt(
            picking, exchange_rate_date=date(2026, 8, 15),
            exchange_rate=32.85, source='manual',
        )
        svl = picking.move_ids.stock_valuation_layer_ids
        self.assertAlmostEqual(sum(svl.mapped('value')), 3285.0, places=2)
        self.assertAlmostEqual(
            product.with_company(self.company).standard_price,
            svl.remaining_value / svl.remaining_qty if svl.remaining_qty else 0,
            places=2,
        )

    def test_fifo_layer_uses_receipt_rate(self):
        product = self._product_with_cost_method('fifo')
        if not product:
            self.skipTest("No FIFO product available on this database.")
        self.product = product
        po = self._create_po(self.usd, 10.0, 10, date(2026, 8, 1))
        picking = po.picking_ids
        self._validate_receipt(
            picking, exchange_rate_date=date(2026, 8, 15),
            exchange_rate=32.85, source='manual',
        )
        svl = picking.move_ids.stock_valuation_layer_ids
        self.assertEqual(len(svl), 1)
        self.assertAlmostEqual(svl.unit_cost, 328.5, places=2)
        self.assertAlmostEqual(svl.value, 3285.0, places=2)

    def test_standard_cost_product_unaffected(self):
        product = self.env['product.product'].search([
            ('type', '=', 'product'),
            ('categ_id.property_cost_method', '=', 'standard'),
            ('company_id', 'in', (False, self.company.id)),
        ], limit=1)
        if not product:
            self.skipTest("No standard-cost product available on this database.")
        self.product = product
        po = self._create_po(self.usd, 10.0, 5, date(2026, 8, 1))
        picking = po.picking_ids
        move = picking.move_ids
        self._validate_receipt(
            picking, exchange_rate_date=date(2026, 8, 15),
            exchange_rate=32.85, source='manual',
        )
        # This module must never touch a standard-cost product's valuation:
        # our gate (_use_receipt_exchange_rate) explicitly excludes
        # cost_method == 'standard', mirroring core's own
        # stock_account _get_in_svl_vals behavior. What core (or another
        # installed module, e.g. biz_receipt_transfer_cost) ends up using
        # as the unit cost for a standard-cost product is out of this
        # module's scope - we only assert our 32.85 rate was NOT applied.
        svl = move.stock_valuation_layer_ids
        unaffected_value = 5 * 10.0 * 32.85
        self.assertNotAlmostEqual(svl.value, unaffected_value, places=2)
