# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import AccessError, UserError


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

    def _reverse_moves(self, default_values_list=None, cancel=False):
        """Every reversal path (Reverse wizard, reconcile un-matching, action_reverse) ends here.

        Asset entries keep their BUZ record in sync: a depreciation reversal marks the
        schedule line reversed and links the reversal; a disposal entry cannot be
        reversed because no flow restores the asset and its schedule.
        """
        disposal_moves = self.filtered('buz_disposal_id')
        if disposal_moves:
            raise UserError(_(
                "รายการบัญชีการจำหน่ายทรัพย์สิน %s กลับรายการไม่ได้ (ยังไม่มีขั้นตอนคืนสถานะทรัพย์สิน)",
                ', '.join(disposal_moves.mapped('name'))))
        depreciation_moves = self.filtered('buz_asset_line_id')
        if depreciation_moves:
            if not self.env.user.has_group('buz_asset_management.group_asset_accounting_manager'):
                raise AccessError(_("คุณไม่มีสิทธิ์กลับรายการค่าเสื่อมราคาทรัพย์สิน"))
            for move in depreciation_moves:
                line = move.buz_asset_line_id
                if line.state != 'posted' or line.move_id != move or line.reversal_move_id:
                    raise UserError(_("งวด %s ไม่อยู่ในสถานะที่กลับรายการได้", line.name))
        reversals = super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)
        for move in depreciation_moves:
            reversal = reversals.filtered(lambda r: r.reversed_entry_id == move)
            if reversal.state != 'posted':
                # A draft/scheduled reversal would leave the line "reversed" while the GL is not.
                raise UserError(_(
                    "การกลับรายการค่าเสื่อมราคาต้องลงบัญชีทันที (ไม่รองรับร่างหรือตั้งเวลาลงบัญชี): %s",
                    move.name))
            line = move.buz_asset_line_id
            # sudo: schedule lines are workflow-guarded; group checked above.
            line.sudo().write({'state': 'reversed', 'reversal_move_id': reversal.id})
            line.asset_id.sudo().message_post(
                author_id=self.env.user.partner_id.id,
                body=_("กลับรายการค่าเสื่อมราคา %(name)s: %(ref)s", name=line.name, ref=reversal.ref or '-'))
        return reversals

    def unlink(self):
        if self.filtered(lambda m: m.buz_asset_line_id or m.buz_disposal_id):
            raise UserError(_("รายการทรัพย์สินลบไม่ได้ กรุณาใช้การกลับรายการ"))
        return super().unlink()
