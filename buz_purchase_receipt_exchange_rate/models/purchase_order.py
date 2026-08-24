# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    exchange_rate_date = fields.Date(
        string="Exchange Rate Date",
        copy=False,
        tracking=True,
        help="Customs declaration date used to look up the exchange rate. "
             "Copied onto the receipt(s) created on confirm, which then "
             "auto-fetches the rate for that date.",
    )
    is_foreign_currency_po = fields.Boolean(
        string="Is Foreign Currency PO",
        compute='_compute_is_foreign_currency_po',
    )

    @api.depends('currency_id', 'company_id.currency_id')
    def _compute_is_foreign_currency_po(self):
        for order in self:
            order.is_foreign_currency_po = bool(
                order.currency_id and order.currency_id != order.company_id.currency_id
            )

    def button_confirm(self):
        res = super().button_confirm()
        for order in self.filtered('exchange_rate_date'):
            order.picking_ids._set_exchange_rate_date_from_po(order.exchange_rate_date)
        return res

    def action_submit_for_review(self):
        for order in self:
            if order.is_foreign_currency_po and not order.exchange_rate_date:
                raise UserError(_(
                    "กรุณาระบุ Exchange Rate Date (วันที่ใบขนสินค้า) ก่อนส่งตรวจสอบ "
                    "เนื่องจาก PO นี้เป็นสกุลเงินต่างประเทศ."))
        return super().action_submit_for_review()
