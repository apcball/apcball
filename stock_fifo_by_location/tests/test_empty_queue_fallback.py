# -*- coding: utf-8 -*-
"""An empty FIFO queue must never silently fall back to the product's standard
price. It either raises, or it logs loudly and falls back — chosen by the
`stock_fifo_by_location.empty_queue_fallback_mode` config parameter.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestEmptyQueueFallback(TransactionCase):

    def setUp(self):
        super().setUp()
        self.fifo_service = self.env['fifo.service']
        self.company = self.env.company
        self.warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.company.id)], limit=1)

        categ = self.env['product.category'].create({
            'name': 'Empty Queue Test Categ',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        self.product = self.env['product.product'].create({
            'name': 'Empty Queue Test Product',
            'type': 'product',
            'categ_id': categ.id,
            'company_id': self.company.id,
            'standard_price': 42.0,
        })
        # No receipts for this product: its per-warehouse FIFO queue is empty.

    def _set_mode(self, mode):
        self.env['ir.config_parameter'].sudo().set_param(
            'stock_fifo_by_location.empty_queue_fallback_mode', mode)

    def test_warning_mode_falls_back_to_standard_price(self):
        self._set_mode('warning')
        result = self.fifo_service.calculate_fifo_cost(
            self.product, self.warehouse, 5.0, self.company.id)
        self.assertEqual(result['layers'], [])
        self.assertAlmostEqual(result['unit_cost'], 42.0)
        self.assertAlmostEqual(result['cost'], 210.0)

    def test_raise_mode_blocks_consumption_from_empty_queue(self):
        self._set_mode('raise')
        with self.assertRaises(UserError):
            self.fifo_service.calculate_fifo_cost(
                self.product, self.warehouse, 5.0, self.company.id)

    def test_raise_mode_also_guards_the_landed_cost_entry_point(self):
        self._set_mode('raise')
        with self.assertRaises(UserError):
            self.fifo_service.calculate_fifo_cost_with_landed_cost(
                self.product, self.warehouse, 5.0, self.company.id)
