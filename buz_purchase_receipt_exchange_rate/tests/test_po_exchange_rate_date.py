# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import UserError

from .test_exchange_rate import ExchangeRateReceiptCase


class TestPoExchangeRateDate(ExchangeRateReceiptCase):

    def _create_draft_po(self, currency, price_unit, qty, date_order, rate_date=None):
        vals = {
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
        }
        if rate_date:
            vals['exchange_rate_date'] = rate_date
        return self.env['purchase.order'].create(vals)

    def test_submit_for_review_blocked_without_exchange_rate_date(self):
        po = self._create_draft_po(self.usd, 10.0, 100, date(2026, 8, 1))
        with self.assertRaises(UserError) as cm:
            po.action_submit_for_review()
        self.assertIn("Exchange Rate Date", str(cm.exception))

    def test_submit_for_review_not_blocked_when_rate_date_set(self):
        po = self._create_draft_po(
            self.usd, 10.0, 100, date(2026, 8, 1), rate_date=date(2026, 8, 15))
        with self.assertRaises(UserError) as cm:
            po.action_submit_for_review()
        # Falls through to buz_po_portal's own checks (e.g. Analytic
        # Account), not blocked by the exchange rate date guard.
        self.assertNotIn("Exchange Rate Date", str(cm.exception))

    def test_submit_for_review_not_blocked_for_company_currency_po(self):
        po = self._create_draft_po(self.thb, 10.0, 100, date(2026, 8, 1))
        with self.assertRaises(UserError) as cm:
            po.action_submit_for_review()
        self.assertNotIn("Exchange Rate Date", str(cm.exception))

    def _create_po_with_rate_date(self, currency, price_unit, qty, date_order, rate_date):
        po = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'company_id': self.company.id,
            'currency_id': currency.id,
            'date_order': date_order,
            'picking_type_id': self.picking_type_in.id,
            'exchange_rate_date': rate_date,
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

    def test_confirm_auto_fetches_rate_on_receipt(self):
        po = self._create_po_with_rate_date(
            self.usd, 10.0, 100, date(2026, 8, 1), date(2026, 8, 15))
        picking = po.picking_ids
        self.assertEqual(picking.exchange_rate_date, date(2026, 8, 15))
        self.assertEqual(picking.exchange_rate_source, 'odoo')
        self.assertAlmostEqual(picking.exchange_rate, 32.85, places=2)

    def test_backorder_inherits_po_rate_date(self):
        po = self._create_po_with_rate_date(
            self.usd, 10.0, 100, date(2026, 8, 1), date(2026, 8, 15))
        picking1 = po.picking_ids
        move = picking1.move_ids
        move.quantity = 40
        move.picked = True
        picking1.with_context(skip_backorder=True).button_validate()

        backorder = self.env['stock.picking'].search([
            ('backorder_id', '=', picking1.id),
        ], limit=1)
        self.assertTrue(backorder)
        self.assertEqual(backorder.exchange_rate_date, date(2026, 8, 15))
        self.assertEqual(backorder.exchange_rate_source, 'odoo')
        self.assertAlmostEqual(backorder.exchange_rate, 32.85, places=2)

    def test_manual_receipt_date_not_overridden(self):
        """If the receipt already got a date (e.g. user set one before PO
        confirm hook ran, or on a re-triggered flow), the PO propagation
        must not clobber it."""
        po = self._create_po_with_rate_date(
            self.usd, 10.0, 100, date(2026, 8, 1), date(2026, 8, 15))
        picking = po.picking_ids
        picking.exchange_rate_date = date(2026, 8, 1)
        picking.action_get_exchange_rate()
        self.assertAlmostEqual(picking.exchange_rate, 32.50, places=2)
        # Re-running propagation must not touch an already-set date.
        picking._set_exchange_rate_date_from_po(date(2026, 8, 15))
        self.assertEqual(picking.exchange_rate_date, date(2026, 8, 1))
        self.assertAlmostEqual(picking.exchange_rate, 32.50, places=2)
