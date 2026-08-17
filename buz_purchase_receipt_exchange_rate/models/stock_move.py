# -*- coding: utf-8 -*-
from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _use_receipt_exchange_rate(self):
        """Gate: only PO-linked incoming moves on a receipt with a manually
        set foreign currency exchange rate use this module's logic."""
        self.ensure_one()
        picking = self.picking_id
        return bool(
            self.purchase_line_id
            and picking
            and picking.picking_type_id.code == 'incoming'
            and picking.is_foreign_currency_receipt
            and picking.exchange_rate > 0
            # Odoo core never calls _get_price_unit() for standard-cost
            # products (it always uses product.standard_price instead), so
            # this module must not touch them either - see stock_account
            # stock_move.py:_get_in_svl_vals.
            and self.product_id.with_company(self.company_id).cost_method != 'standard'
        )

    def _get_currency_convert_date(self):
        if self._use_receipt_exchange_rate() and self.picking_id.exchange_rate_date:
            return self.picking_id.exchange_rate_date
        return super()._get_currency_convert_date()

    def _get_price_unit(self):
        self.ensure_one()
        if not self._use_receipt_exchange_rate():
            return super()._get_price_unit()

        picking = self.picking_id
        line = self.purchase_line_id
        price_order_ccy = line._get_gross_price_unit()

        if picking.exchange_rate_source == 'manual':
            return price_order_ccy * picking.exchange_rate

        order_currency = line.currency_id
        company_currency = self.company_id.currency_id
        return order_currency._convert(
            price_order_ccy, company_currency, self.company_id,
            picking.exchange_rate_date, round=False,
        )

    def _generate_valuation_lines_data(self, partner_id, qty, debit_value, credit_value,
                                        debit_account_id, credit_account_id, svl_id, description):
        rslt = super()._generate_valuation_lines_data(
            partner_id, qty, debit_value, credit_value,
            debit_account_id, credit_account_id, svl_id, description,
        )
        if not self._use_receipt_exchange_rate():
            return rslt
        picking = self.picking_id
        if picking.exchange_rate_source != 'manual':
            return rslt
        purchase_currency = self.purchase_line_id.currency_id
        company_currency = self.company_id.currency_id
        if purchase_currency == company_currency or not picking.exchange_rate:
            return rslt
        svl = self.env['stock.valuation.layer'].browse(svl_id)
        if svl.account_move_line_id:
            # A price-diff correction line: leave core's own logic untouched.
            return rslt
        for key in ('credit_line_vals', 'debit_line_vals'):
            vals = rslt.get(key)
            if vals and vals.get('currency_id') == purchase_currency.id:
                vals['amount_currency'] = vals['balance'] / picking.exchange_rate
        return rslt
