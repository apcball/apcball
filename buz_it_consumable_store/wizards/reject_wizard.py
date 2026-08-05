from odoo import fields, models, _
from odoo.exceptions import UserError


class BuzItConsumableRejectWizard(models.TransientModel):
    _name = 'buz.it.consumable.reject.wizard'
    _description = 'Reject Consumable Line'

    line_id = fields.Many2one(
        'buz.it.consumable.request.line',
        string='รายการ',
        required=True,
        readonly=True,
    )
    consumable_id = fields.Many2one(
        'buz.it.consumable',
        related='line_id.consumable_id',
        string='สินค้า',
        readonly=True,
    )
    unit = fields.Char(
        related='line_id.unit',
        string='หน่วย',
        readonly=True,
    )
    requested_qty = fields.Float(
        related='line_id.requested_qty',
        string='จำนวนที่ขอ',
        readonly=True,
        digits=(16, 0),
    )
    reason = fields.Text(string='เหตุผลที่ปฏิเสธ', required=True)

    def action_reject(self):
        self.ensure_one()
        if not self.env.user.has_group('buz_it_helpdesk.group_it_support_agent'):
            raise UserError(_('เฉพาะ Support Agent เท่านั้นที่ปฏิเสธรายการได้'))
        line = self.line_id
        line.with_context(buz_consumable_transition=True).write({
            'rejected': True,
            'reason': self.reason,
        })
        line.request_id._recompute_state()
        return line.request_id.get_formview_action()
