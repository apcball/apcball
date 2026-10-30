# -*- coding: utf-8 -*-
"""`shortage_policy=error` must block an outgoing move that would drive the
warehouse's valuation ledger negative, even when negative_balance_mode is
'warning'. `fallback` keeps the old warning-only behaviour.
"""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestShortagePolicy(TransactionCase):

    def setUp(self):
        super().setUp()
        self.warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        categ = self.env['product.category'].create({
            'name': 'Shortage Policy Test Categ',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        self.product = self.env['product.product'].create({
            'name': 'Shortage Policy Test Product',
            'type': 'product',
            'categ_id': categ.id,
            'standard_price': 10.0,
        })
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('stock_fifo_by_location.negative_balance_mode', 'warning')

    def _move_out(self, qty):
        """Book an outgoing valuation layer for a warehouse that holds nothing."""
        customers = self.env.ref('stock.stock_location_customers')
        move = self.env['stock.move'].create({
            'name': 'Shortage Policy Out',
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'location_dest_id': customers.id,
        })
        self.env['stock.valuation.layer'].create({
            'product_id': self.product.id,
            'stock_move_id': move.id,
            'warehouse_id': self.warehouse.id,
            'company_id': self.env.company.id,
            'quantity': -qty,
            'unit_cost': 10.0,
            'value': -qty * 10.0,
            'description': 'Shortage Policy Out',
        })

    def _set_policy(self, policy):
        self.env['ir.config_parameter'].sudo().set_param(
            'stock_fifo_by_location.shortage_policy', policy)

    def test_error_policy_blocks_in_warning_mode(self):
        self._set_policy('error')
        with self.assertRaises(ValidationError):
            self._move_out(5.0)

    def test_fallback_policy_allows_in_warning_mode(self):
        self._set_policy('fallback')
        self._move_out(5.0)
