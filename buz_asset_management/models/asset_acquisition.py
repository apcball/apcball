# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import float_compare


class BuzAssetAcquisition(models.Model):
    """Allocation of (part of) a posted vendor-bill line to one asset.

    Allocations are in company currency (the line's ``balance``), so a bill in
    a foreign currency capitalizes the amount that was actually booked in the GL.
    """
    _name = 'buz.asset.acquisition'
    _description = 'การจัดสรรใบแจ้งหนี้ผู้ขายเป็นทรัพย์สิน'
    _order = 'id desc'
    _check_company_auto = True

    asset_id = fields.Many2one(
        'buz.asset', required=True, index=True, ondelete='cascade', check_company=True, string='ทรัพย์สิน')
    move_line_id = fields.Many2one(
        'account.move.line', required=True, index=True, ondelete='restrict', check_company=True,
        string='รายการในใบแจ้งหนี้')
    move_id = fields.Many2one(
        'account.move', related='move_line_id.move_id', store=True, index=True, string='ใบแจ้งหนี้ผู้ขาย')
    company_id = fields.Many2one('res.company', related='asset_id.company_id', store=True, index=True, string='บริษัท')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True, string='สกุลเงิน')
    amount = fields.Monetary(currency_field='currency_id', required=True, string='จำนวนที่จัดสรร')

    _sql_constraints = [
        ('asset_line_uniq', 'unique(asset_id, move_line_id)',
         'ทรัพย์สินเดียวกันจัดสรรรายการเดียวกันได้เพียงครั้งเดียว'),
        ('amount_positive', 'CHECK(amount > 0)', 'จำนวนที่จัดสรรต้องมากกว่าศูนย์'),
    ]

    @api.model
    def _eligible_amount(self, move_line):
        """Capitalizable amount of a bill line, or 0 when the line is not eligible."""
        move = move_line.move_id
        if (move.move_type != 'in_invoice' or move.state != 'posted'
                or move_line.display_type != 'product' or move_line.balance <= 0):
            return 0.0
        # A line already routed to the legacy om_account_asset engine must not be capitalized twice.
        if 'asset_category_id' in move_line._fields and move_line.asset_category_id:
            return 0.0
        return move_line.balance + self._non_recoverable_vat(move_line)

    @api.model
    def _non_recoverable_vat(self, move_line):
        """Non-recoverable VAT of a bill line in company currency (taxes flagged for capitalization)."""
        taxes = move_line.tax_ids.filtered('buz_vat_non_recoverable')
        if not taxes:
            return 0.0
        result = taxes.compute_all(
            move_line.price_unit * (1 - move_line.discount / 100.0), currency=move_line.currency_id,
            quantity=move_line.quantity, product=move_line.product_id, partner=move_line.partner_id)
        vat = sum(tax['amount'] for tax in result['taxes'])
        if move_line.amount_currency and move_line.currency_id != move_line.company_currency_id:
            vat *= abs(move_line.balance / move_line.amount_currency)
        return move_line.company_currency_id.round(max(vat, 0.0))

    @api.model
    def _allocated_amount(self, move_line, exclude=None):
        domain = [('move_line_id', '=', move_line.id)]
        if exclude:
            domain.append(('id', 'not in', exclude.ids))
        return sum(self.sudo().search(domain).mapped('amount'))

    @api.constrains('move_line_id', 'amount', 'asset_id')
    def _check_allocation(self):
        for acq in self:
            line = acq.move_line_id
            eligible = self._eligible_amount(line)
            rounding = acq.currency_id.rounding
            if float_compare(eligible, 0.0, precision_rounding=rounding) <= 0:
                raise ValidationError(_(
                    "รายการ '%s' ไม่เข้าเงื่อนไขเป็นทรัพย์สิน (ต้องเป็นรายการสินค้า/บริการของใบแจ้งหนี้ผู้ขายที่ลงบัญชีแล้ว)",
                    line.display_name))
            if line.company_id != acq.company_id:
                raise ValidationError(_("บริษัทของใบแจ้งหนี้และทรัพย์สินต้องตรงกัน"))
            total = self._allocated_amount(line)
            if float_compare(total, eligible, precision_rounding=rounding) > 0:
                raise ValidationError(_(
                    "จัดสรรรายการ '%(line)s' เกินจำนวนที่มี: จัดสรรแล้ว %(total)s จากทั้งหมด %(eligible)s",
                    line=line.display_name, total=total, eligible=eligible))

    def write(self, vals):
        if not self.env.su and {'move_line_id', 'amount', 'asset_id'} & set(vals):
            raise AccessError(_("แก้ไขการจัดสรรโดยตรงไม่ได้ กรุณาลบทรัพย์สินร่างแล้วจัดสรรใหม่"))
        return super().write(vals)
