from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BuzItConsumableAddWizard(models.TransientModel):
    _name = 'buz.it.consumable.add.wizard'
    _description = 'Add Consumable to Request'

    consumable_id = fields.Many2one(
        'buz.it.consumable',
        string='สินค้า',
        required=True,
        readonly=True,
    )
    unit = fields.Char(
        related='consumable_id.unit',
        string='หน่วย',
        readonly=True,
    )
    on_hand_qty = fields.Float(
        related='consumable_id.on_hand_qty',
        string='ยอดคงเหลือ',
        readonly=True,
        digits=(16, 0),
    )
    max_per_request = fields.Float(
        related='consumable_id.max_per_request',
        string='สูงสุดต่อคำขอ',
        readonly=True,
        digits=(16, 0),
    )
    qty = fields.Float(
        string='จำนวน',
        digits=(16, 0),
        required=True,
        default=1.0,
    )

    @api.onchange('qty')
    def _onchange_qty(self):
        if (
            self.consumable_id
            and self.qty
            and self.consumable_id.max_per_request
            and self.qty > self.consumable_id.max_per_request
        ):
            self.qty = self.consumable_id.max_per_request
            return {
                'warning': {
                    'title': _('เกินจำนวนสูงสุด'),
                    'message': _('จำนวนสูงสุดต่อคำขอคือ %s %s') % (
                        self.consumable_id.max_per_request, self.unit,
                    ),
                },
            }
        return {}

    def action_add(self):
        self.ensure_one()
        if self.qty <= 0:
            raise UserError(_('จำนวนต้องมากกว่า 0'))
        if not self.consumable_id.active or not self.consumable_id.is_published:
            raise UserError(_('สินค้านี้ไม่สามารถเบิกได้'))
        max_qty = self.consumable_id.max_per_request
        request = self.env['buz.it.consumable.request']._get_or_create_cart()
        line = self.env['buz.it.consumable.request.line'].search([
            ('request_id', '=', request.id),
            ('consumable_id', '=', self.consumable_id.id),
            ('rejected', '=', False),
            ('state', '=', 'pending'),
        ], limit=1)
        existing = line.requested_qty if line else 0.0
        new_qty = existing + self.qty
        if max_qty and new_qty > max_qty:
            raise UserError(_('รวมจำนวนที่ขอเกินสูงสุดต่อคำขอ (%s %s)') % (
                max_qty, self.unit,
            ))
        if line:
            line.with_context(buz_consumable_transition=True).write({
                'requested_qty': new_qty,
            })
        else:
            self.env['buz.it.consumable.request.line'].create({
                'request_id': request.id,
                'consumable_id': self.consumable_id.id,
                'requested_qty': self.qty,
            })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('เพิ่มในรายการเบิกแล้ว'),
                'message': _('%s %s %s อยู่ในรายการเบิกครั้งนี้') % (
                    self.qty, self.unit, self.consumable_id.name,
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
