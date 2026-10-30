# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    buz_asset_line_id = fields.Many2one(
        'buz.asset.depreciation.line', string='งวดค่าเสื่อมราคาทรัพย์สิน',
        copy=False, index=True, readonly=True, ondelete='restrict')

    buz_disposal_id = fields.Many2one(
        'buz.asset.disposal', string='การจำหน่ายทรัพย์สิน',
        copy=False, index=True, readonly=True, ondelete='restrict')

    def _buz_has_asset_acquisition(self):
        return bool(self.env['buz.asset.acquisition'].sudo().search_count([('move_id', 'in', self.ids)]))

    def action_buz_register_assets(self):
        self.ensure_one()
        if self.move_type != 'in_invoice' or self.state != 'posted':
            raise UserError(_("ใช้ได้เฉพาะใบแจ้งหนี้ผู้ขายที่ลงบัญชีแล้ว"))
        return {
            'type': 'ir.actions.act_window', 'res_model': 'buz.asset.register.wizard',
            'name': _('สร้างทรัพย์สินจากใบแจ้งหนี้'), 'view_mode': 'form', 'target': 'new',
            'context': {'default_move_id': self.id}}

    def button_draft(self):
        if self._buz_has_asset_acquisition():
            raise UserError(_("ใบแจ้งหนี้นี้ถูกใช้สร้างทรัพย์สินแล้ว ตั้งกลับเป็นร่างไม่ได้ กรุณาใช้ใบลดหนี้หรือกลับรายการ"))
        if self.filtered(lambda m: m.buz_asset_line_id or m.buz_disposal_id):
            raise UserError(_("รายการทรัพย์สินตั้งกลับเป็นร่างไม่ได้ กรุณาใช้การกลับรายการ"))
        return super().button_draft()

    def button_cancel(self):
        if self._buz_has_asset_acquisition():
            raise UserError(_("ใบแจ้งหนี้นี้ถูกใช้สร้างทรัพย์สินแล้ว ยกเลิกไม่ได้"))
        return super().button_cancel()

    def unlink(self):
        if self.filtered(lambda m: m.buz_asset_line_id or m.buz_disposal_id):
            raise UserError(_("รายการทรัพย์สินลบไม่ได้ กรุณาใช้การกลับรายการ"))
        return super().unlink()
