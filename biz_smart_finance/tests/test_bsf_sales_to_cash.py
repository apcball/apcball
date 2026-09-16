# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestBsfSalesToCash(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = cls.env["biz.smart.finance.dashboard"]
        cls.partner = cls.env["res.partner"].create({
            "name": "Sales to Cash customer", "bsf_billing_mode": "monthly",
            "bsf_billing_days": "10,25,31",
        })

    def test_next_billing_day_and_month_end(self):
        self.assertEqual(self.engine._sales_to_cash_bill_date(self.partner, date(2028, 2, 26)), date(2028, 2, 29))
        self.assertEqual(self.engine._sales_to_cash_bill_date(self.partner, date(2028, 2, 29)), date(2028, 2, 29))
        self.assertEqual(self.engine._sales_to_cash_bill_date(self.partner, date(2028, 3, 1)), date(2028, 3, 10))

    def test_invalid_billing_days_need_review(self):
        self.partner.bsf_billing_days = "fortnightly"
        self.assertFalse(self.engine._sales_to_cash_bill_date(self.partner, date(2028, 3, 1)))

    def test_delivery_plan_cannot_exceed_ordered_quantity(self):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        product = self.env["product.product"].create({"name": "Sales to Cash test item", "type": "service"})
        line = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": product.id, "name": "item", "product_uom_qty": 1,
            "price_unit": 100,
        })
        with self.assertRaises(ValidationError):
            self.env["biz.smart.finance.delivery.plan"].create({
                "sale_order_id": order.id, "sale_line_id": line.id,
                "delivery_date": date(2028, 3, 1), "quantity": 2,
            })

    def _forecast_context(self, **filters):
        engine = self.engine.sudo()
        f = engine._normalize_filters(dict(company_id=self.env.company.id, **filters))
        return f, engine._build_shared(f)

    def _sale(self, quantity=10, currency=None):
        from odoo import fields
        values = {'partner_id': self.partner.id, 'state': 'sale',
                  'commitment_date': fields.Datetime.now(),
                  'payment_term_id': self.env.ref('account.account_payment_term_immediate').id}
        if currency:
            values['pricelist_id'] = self.env['product.pricelist'].create({
                'name': 'Cash review FX', 'currency_id': currency.id}).id
        order = self.env['sale.order'].create(values)
        product = self.env['product.product'].create({'name': 'Cash review service', 'type': 'service'})
        line = self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': product.id, 'name': 'service',
            'product_uom_qty': quantity, 'price_unit': 100, 'tax_id': [(5, 0, 0)]})
        self.partner.bsf_billing_mode = 'delivery'
        return order, line

    def test_partial_invoice_consumes_earliest_delivery_plans(self):
        from odoo import fields
        from dateutil.relativedelta import relativedelta
        order, line = self._sale()
        today = fields.Date.today()
        plans = self.env['biz.smart.finance.delivery.plan'].create([
            {'sale_order_id': order.id, 'sale_line_id': line.id, 'quantity': 5,
             'delivery_date': today + relativedelta(days=offset)} for offset in (5, 15)])
        # Isolate the quantity supplied by the invoice computation.
        line.qty_invoiced = 6
        f, shared = self._forecast_context(include_sales_to_cash=True)
        sources = self.engine._forecast_sources(f, shared)
        rows = [r for r in sources['sales_to_cash'] if r['sale_line_id'] == line.id]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['plan_id'], plans[1].id)
        self.assertAlmostEqual(rows[0]['amount'], 400 * shared['fx'][order.company_id.id], places=2)

    def test_unplanned_balance_is_not_lost_after_partial_invoice(self):
        from odoo import fields
        order, line = self._sale()
        self.env['biz.smart.finance.delivery.plan'].create({
            'sale_order_id': order.id, 'sale_line_id': line.id, 'quantity': 5,
            'delivery_date': fields.Date.today()})
        line.qty_invoiced = 6
        f, shared = self._forecast_context(include_sales_to_cash=True)
        rows = [r for r in self.engine._forecast_sources(f, shared)['sales_to_cash']
                if r['sale_line_id'] == line.id]
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]['plan_id'])
        self.assertAlmostEqual(rows[0]['amount'], 400 * shared['fx'][order.company_id.id], places=2)

    def test_foreign_sale_is_converted_before_presentation(self):
        from odoo import fields
        currency = self.env['res.currency'].create({'name': 'QFX', 'symbol': 'Q', 'rounding': .01})
        self.env['res.currency.rate'].create({
            'currency_id': currency.id, 'company_id': self.env.company.id,
            'name': fields.Date.today(), 'rate': .025})
        order, line = self._sale(currency=currency)
        f, shared = self._forecast_context(include_sales_to_cash=True)
        rows = [r for r in self.engine._forecast_sources(f, shared)['sales_to_cash']
                if r['sale_line_id'] == line.id]
        expected = currency._convert(1000, order.company_id.currency_id,
                                     order.company_id, f['as_of'], round=False) * shared['fx'][order.company_id.id]
        self.assertNotAlmostEqual(expected, 1000 * shared['fx'][order.company_id.id], places=2)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['amount'], expected, places=2)

    def _collection_grids(self, items, followups=()):
        from unittest.mock import patch
        f, shared = self._forecast_context(include_sales_to_cash=False)
        shared['ar_items'] = items
        with patch.object(type(self.env['biz.smart.finance.collection.followup']), 'search', return_value=followups):
            weekly = self.engine._build_cash_forecast(f, shared)
        self.engine._build_margin(f, shared)
        self.engine._build_forecast(f, shared)
        return f, shared, weekly

    def test_external_invoices_keep_distinct_collection_months(self):
        from odoo import fields
        from dateutil.relativedelta import relativedelta
        today = fields.Date.today()
        dates = [today + relativedelta(months=i, day=1) for i in (1, 2)]
        items = [{'external': True, 'date': today, 'date_maturity': day,
                  'amount_residual': amount} for day, amount in zip(dates, (100, 200))]
        _, baseline, _ = self._collection_grids([])
        _, shared, _ = self._collection_grids(items)
        delta = [a-b for a, b in zip(shared['fc_basis']['legs']['collections'],
                                    baseline['fc_basis']['legs']['collections'])]
        self.assertAlmostEqual(delta[1], 100)
        self.assertAlmostEqual(delta[2], 200)
        self.assertAlmostEqual(sum(delta), 300)

    def test_partial_promise_matches_weekly_and_monthly_with_fx(self):
        from odoo import fields
        from types import SimpleNamespace
        today = fields.Date.today()
        f, shared = self._forecast_context()
        rate = shared['fx'][self.env.company.id]
        items = [{'id': 123, 'date': today, 'date_maturity': today, 'amount_residual': 100000 * rate}]
        followup = SimpleNamespace(move_line_id=SimpleNamespace(id=123), promised_date=today,
                                   promised_amount=20000, dispute=False, company_id=self.env.company)
        _, baseline, base_weekly = self._collection_grids([])
        _, shared, weekly = self._collection_grids(items, [followup])
        weekly_delta = sum(r['inflow_collections'] for r in weekly['rows']) - sum(r['inflow_collections'] for r in base_weekly['rows'])
        monthly_delta = sum(shared['fc_basis']['legs']['collections']) - sum(baseline['fc_basis']['legs']['collections'])
        self.assertAlmostEqual(weekly_delta, 20000 * rate, places=2)
        self.assertAlmostEqual(monthly_delta, 20000 * rate, places=2)
