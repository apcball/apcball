# -*- coding: utf-8 -*-
"""
Guard: block quantity changes on move lines of an already-done move.

Root cause this prevents (OJ00078211 incident, 2026-08-19):
Valuation layers (SVL) are only created once, when stock.move._action_done()
runs. If a move_line is added or its quantity edited AFTER the move is
already 'done' (e.g. a second barcode scan landing after the first save),
the physical quantity (stock.move.quantity / quants) changes but no SVL
is ever created or corrected for the delta — stock and valuation silently
diverge. Odoo core does not re-trigger valuation on such edits.

Fix: refuse the edit. Corrections to a done move must go through a proper
stock document (return, backorder, inventory adjustment) so valuation is
created through the normal, audited path.
"""

from odoo import api, models, _
from odoo.exceptions import UserError

QTY_FIELDS = ('quantity', 'qty_done', 'quantity_product_uom')


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def write(self, vals):
        if any(f in vals for f in QTY_FIELDS) and not self.env.context.get('bypass_done_move_line_guard'):
            for line in self:
                if line.move_id and line.move_id.state == 'done':
                    raise UserError(_(
                        'ไม่สามารถแก้ไขจำนวนใน Move Line ของเอกสารที่ยืนยันแล้ว (Done) ได้\n'
                        'อ้างอิง: %(ref)s\n\n'
                        'สาเหตุ: Valuation (FIFO cost) ถูกสร้างครั้งเดียวตอน validate เท่านั้น '
                        'การแก้ไขจำนวนภายหลังจะทำให้ยอด stock จริงกับ valuation ไม่ตรงกัน '
                        'โดยไม่มีการแจ้งเตือนใด ๆ\n\n'
                        'กรุณาใช้ Return / สร้าง Backorder / Inventory Adjustment แทน '
                        'เพื่อให้ valuation ถูกสร้างผ่านขั้นตอนปกติ'
                    ) % {'ref': line.move_id.reference or line.move_id.name})
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('bypass_done_move_line_guard'):
            move_ids = {v['move_id'] for v in vals_list if v.get('move_id')}
            if move_ids:
                done_moves = self.env['stock.move'].browse(move_ids).filtered(lambda m: m.state == 'done')
                if done_moves:
                    raise UserError(_(
                        'ไม่สามารถเพิ่ม Move Line ใหม่ในเอกสารที่ยืนยันแล้ว (Done) ได้\n'
                        'อ้างอิง: %(ref)s\n\n'
                        'กรุณาใช้ Return / สร้าง Backorder / Inventory Adjustment แทน'
                    ) % {'ref': ', '.join(done_moves.mapped(lambda m: m.reference or m.name))})
        return super().create(vals_list)
