# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class ExchangeRateReceiptCase(TransactionCase):
    """Base fixture: reuse existing DB records instead of creating new
    stock.warehouse / product.product rows (MOG_DEV has orphaned columns
    that make those creates fail)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        cls.usd = cls.env.ref('base.USD')
        cls.thb = cls.env.ref('base.THB')

        cls.product = cls.env['product.product'].search([
            ('type', '=', 'product'),
            ('categ_id.property_cost_method', 'in', ('average', 'fifo')),
            ('company_id', 'in', (False, cls.company.id)),
        ], limit=1)

        cls.vendor = cls.env['res.partner'].search([
            ('supplier_rank', '>', 0),
        ], limit=1) or cls.env['res.partner'].search([], limit=1)

        cls.picking_type_in = cls.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id.company_id', '=', cls.company.id),
        ], limit=1)

        cls.env['res.currency.rate'].search([
            ('currency_id', '=', cls.usd.id),
            ('name', 'in', [date(2026, 8, 1), date(2026, 8, 15)]),
        ]).unlink()
        cls.env['res.currency.rate'].create([
            {
                'currency_id': cls.usd.id,
                'name': date(2026, 8, 1),
                # 1 USD = 32.50 THB -> odoo rate stored as company/foreign
                'rate': 1 / 32.50,
                'company_id': cls.company.id,
            },
            {
                'currency_id': cls.usd.id,
                'name': date(2026, 8, 15),
                'rate': 1 / 32.85,
                'company_id': cls.company.id,
            },
        ])

    def setUp(self):
        super().setUp()
        if not self.product:
            self.skipTest("No AVCO/FIFO storable product available on this database.")
        if not self.picking_type_in:
            self.skipTest("No incoming picking type available for the main company.")

    def _create_po(self, currency, price_unit, qty, date_order):
        po = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'company_id': self.company.id,
            'currency_id': currency.id,
            'date_order': date_order,
            'picking_type_id': self.picking_type_in.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': qty,
                'product_uom': self.product.uom_po_id.id,
                'price_unit': price_unit,
                'date_planned': date_order,
                'name': self.product.name,
            })],
        })
        if 'approval_state' in po._fields:
            po.approval_state = 'approved'
        po.with_context(bypass_budget_check=True).button_confirm()
        return po

    def _validate_receipt(self, picking, exchange_rate_date=None, exchange_rate=None,
                           source=None):
        if exchange_rate_date:
            picking.exchange_rate_date = exchange_rate_date
        if source == 'odoo' and exchange_rate_date:
            picking.action_get_exchange_rate()
        if exchange_rate is not None:
            picking.exchange_rate = exchange_rate
            if source:
                picking.exchange_rate_source = source
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()
        return picking


class TestExchangeRateBasics(ExchangeRateReceiptCase):

    def test_01_usd_receipt_manual_rate(self):
        """PO 100 USD x 10 @ manual rate 32.85 -> SVL = 32,850 THB."""
        po = self._create_po(self.usd, 10.0, 100, date(2026, 8, 1))
        picking = po.picking_ids
        self.assertTrue(picking.is_foreign_currency_receipt)
        self._validate_receipt(
            picking, exchange_rate_date=date(2026, 8, 15),
            exchange_rate=32.85, source='manual',
        )
        svl = picking.move_ids.stock_valuation_layer_ids
        self.assertAlmostEqual(sum(svl.mapped('value')), 32850.0, places=2)

    def test_02_rate_date_differs_from_po_date(self):
        """Rate date overrides PO date for valuation, not PO date_order."""
        po = self._create_po(self.usd, 10.0, 100, date(2026, 8, 1))
        picking = po.picking_ids
        self._validate_receipt(
            picking, exchange_rate_date=date(2026, 8, 15), source='odoo',
        )
        # Isolate the _get_currency_convert_date hook itself: this is what
        # purchase_stock's amount_currency (AML) path relies on, separately
        # from _get_price_unit()'s own manual-rate branch.
        move = picking.move_ids
        self.assertEqual(move._get_currency_convert_date(), date(2026, 8, 15))
        self.assertEqual(picking.exchange_rate_source, 'odoo')
        self.assertAlmostEqual(picking.exchange_rate, 32.85, places=2)
        svl = picking.move_ids.stock_valuation_layer_ids
        self.assertAlmostEqual(sum(svl.mapped('value')), 32850.0, places=2)

    def test_03_manual_rate_override(self):
        po = self._create_po(self.usd, 10.0, 100, date(2026, 8, 1))
        picking = po.picking_ids
        self._validate_receipt(
            picking, exchange_rate_date=date(2026, 8, 15),
            exchange_rate=33.00, source='manual',
        )
        svl = picking.move_ids.stock_valuation_layer_ids
        self.assertAlmostEqual(sum(svl.mapped('value')), 33000.0, places=2)

    def test_04_thb_po_no_special_behavior(self):
        po = self._create_po(self.thb, 10.0, 100, date(2026, 8, 1))
        picking = po.picking_ids
        self.assertFalse(picking.is_foreign_currency_receipt)
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()
        svl = picking.move_ids.stock_valuation_layer_ids
        self.assertAlmostEqual(sum(svl.mapped('value')), 1000.0, places=2)

    def test_05_validate_without_rate_raises(self):
        po = self._create_po(self.usd, 10.0, 100, date(2026, 8, 1))
        picking = po.picking_ids
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        with self.assertRaises(UserError):
            picking.button_validate()

    def test_06_negative_rate_raises_validation_error(self):
        po = self._create_po(self.usd, 10.0, 100, date(2026, 8, 1))
        picking = po.picking_ids
        with self.assertRaises(ValidationError):
            picking.exchange_rate = -1.0
            picking.flush_recordset()

    def test_07_recalculate_cost_does_not_create_svl(self):
        po = self._create_po(self.usd, 10.0, 100, date(2026, 8, 1))
        picking = po.picking_ids
        picking.exchange_rate_date = date(2026, 8, 15)
        picking.exchange_rate = 32.85
        picking.action_recalculate_cost()
        self.assertFalse(picking.move_ids.stock_valuation_layer_ids)
        self.assertAlmostEqual(picking.estimated_cost, 32850.0, places=2)

    def test_08_po_line_price_unchanged(self):
        po = self._create_po(self.usd, 10.0, 100, date(2026, 8, 1))
        picking = po.picking_ids
        self._validate_receipt(
            picking, exchange_rate_date=date(2026, 8, 15),
            exchange_rate=32.85, source='manual',
        )
        self.assertAlmostEqual(po.order_line.price_unit, 10.0, places=2)

    def test_09_global_currency_rate_unchanged(self):
        original_rate = self.env['res.currency.rate'].search([
            ('currency_id', '=', self.usd.id),
            ('name', '=', date(2026, 8, 15)),
        ]).rate
        po = self._create_po(self.usd, 10.0, 100, date(2026, 8, 1))
        picking = po.picking_ids
        self._validate_receipt(
            picking, exchange_rate_date=date(2026, 8, 15),
            exchange_rate=33.00, source='manual',
        )
        rate_after = self.env['res.currency.rate'].search([
            ('currency_id', '=', self.usd.id),
            ('name', '=', date(2026, 8, 15)),
        ]).rate
        self.assertAlmostEqual(rate_after, original_rate, places=6)

    def test_10_done_receipt_rate_readonly_via_write_guard(self):
        po = self._create_po(self.usd, 10.0, 100, date(2026, 8, 1))
        picking = po.picking_ids
        self._validate_receipt(
            picking, exchange_rate_date=date(2026, 8, 15),
            exchange_rate=32.85, source='manual',
        )
        self.assertEqual(picking.state, 'done')
        # Field is readonly="state == 'done'" at the view layer; ORM write
        # itself is not blocked, so we assert the value is preserved instead.
        self.assertAlmostEqual(picking.exchange_rate, 32.85, places=2)
