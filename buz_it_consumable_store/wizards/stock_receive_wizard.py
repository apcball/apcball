from odoo import fields, models, _
from odoo.exceptions import UserError


class BuzItStockReceiveWizard(models.TransientModel):
    _name = 'buz.it.stock.receive.wizard'
    _description = 'Receive IT Stock'

    line_ids = fields.One2many(
        'buz.it.stock.receive.line',
        'wizard_id',
        string='รายการ',
    )
    default_location_id = fields.Many2one(
        'buz.it.stock.location',
        string='Location (ค่าเริ่มต้น)',
        domain="[('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(
        'res.company',
        string='บริษัท',
        required=True,
        default=lambda self: self.env.company,
    )
    move_date = fields.Date(
        string='วันที่รับ',
        required=True,
        default=fields.Date.context_today,
    )
    note = fields.Text(string='หมายเหตุ')

    def action_receive(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('กรุณาเพิ่มรายการอย่างน้อย 1 รายการ'))
        for line in self.line_ids:
            if line.qty <= 0:
                raise UserError(_('จำนวนรับเข้าของ %s ต้องมากกว่า 0') % (
                    line.consumable_id.display_name,
                ))
            location = line.location_id or self.default_location_id
            if not location:
                raise UserError(_('กรุณาระบุ Location ของ %s') % (
                    line.consumable_id.display_name,
                ))
            if location.company_id != line.consumable_id.company_id:
                raise UserError(_('%s และ Location %s ต้องอยู่บริษัทเดียวกัน') % (
                    line.consumable_id.display_name, location.name,
                ))
            quant = self.env['buz.it.stock.quant'].sudo().search([
                ('consumable_id', '=', line.consumable_id.id),
                ('location_id', '=', location.id),
            ], limit=1)
            if not quant:
                quant = self.env['buz.it.stock.quant'].sudo().create({
                    'consumable_id': line.consumable_id.id,
                    'location_id': location.id,
                    'qty': 0.0,
                })
            quant.qty += line.qty
            self.env['buz.it.stock.history'].sudo().create({
                'move_type': 'in',
                'consumable_id': line.consumable_id.id,
                'location_id': location.id,
                'qty': line.qty,
                'move_date': self.move_date,
                'reference': _('รับของเข้า'),
                'note': self.note,
            })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('รับของเข้าแล้ว'),
                'message': _('รับของเข้า %d รายการ') % len(self.line_ids),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class BuzItStockReceiveLine(models.TransientModel):
    _name = 'buz.it.stock.receive.line'
    _description = 'IT Stock Receive Line'

    wizard_id = fields.Many2one(
        'buz.it.stock.receive.wizard',
        ondelete='cascade',
    )
    consumable_id = fields.Many2one(
        'buz.it.consumable',
        string='สินค้า',
        required=True,
    )
    qty = fields.Float(
        string='จำนวน',
        digits=(16, 0),
        required=True,
    )
    location_id = fields.Many2one(
        'buz.it.stock.location',
        string='Location',
        domain="[('company_id', '=', consumable_id.company_id)]",
    )
    company_id = fields.Many2one(
        'res.company',
        related='consumable_id.company_id',
        string='บริษัท',
    )
