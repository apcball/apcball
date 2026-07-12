from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosLiteStartSaleWizard(models.TransientModel):
    _name = 'pos.lite.start.sale.wizard'
    _description = 'POS Lite Start Sale — เลือกพนักงานขาย'

    session_id = fields.Many2one(
        'pos.lite.session', required=True, readonly=True,
    )
    employee_id = fields.Many2one(
        'hr.employee', string='พนักงานขาย', required=True,
        domain="[('id', 'in', allowed_employee_ids)]",
    )
    allowed_employee_ids = fields.Many2many(
        'hr.employee', compute='_compute_allowed_employees',
    )
    channel = fields.Selection([
        ('phone', 'Phone'),
        ('line', 'LINE'),
        ('walkin', 'Walk-in'),
        ('other', 'Other'),
    ], default='walkin', required=True, string='ช่องทาง')
    trade_channel = fields.Selection(
        selection='_selection_trade_channel',
        string='Trade Channel',
        help='Marketplace trade channel for settlement grouping.',
    )

    @api.model
    def _selection_trade_channel(self):
        """Dynamic selection mirroring sale.order.trade_channel (injected by marketplace_settlement)."""
        from odoo.addons.pos_lite.models.pos_order import _get_trade_channel_selection
        return _get_trade_channel_selection(self)

    @api.depends('session_id')
    def _compute_allowed_employees(self):
        for wizard in self:
            employees = wizard.session_id.employee_ids
            if wizard.session_id.employee_id and wizard.session_id.employee_id not in employees:
                employees |= wizard.session_id.employee_id
            wizard.allowed_employee_ids = employees

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'session_id' in fields_list and not res.get('session_id'):
            active_id = self.env.context.get('default_session_id') or self.env.context.get('active_id')
            if active_id:
                res['session_id'] = active_id
        session_id = res.get('session_id')
        if session_id:
            session = self.env['pos.lite.session'].browse(session_id)
            # Pre-fill จากค่าที่จำไว้ใน session
            if 'employee_id' in fields_list and not res.get('employee_id'):
                if session.current_employee_id:
                    res['employee_id'] = session.current_employee_id.id
                else:
                    employees = session.employee_ids
                    if session.employee_id and session.employee_id not in employees:
                        employees |= session.employee_id
                    if len(employees) == 1:
                        res['employee_id'] = employees.id
            if 'channel' in fields_list and not res.get('channel'):
                if session.current_channel:
                    res['channel'] = session.current_channel
            if 'trade_channel' in fields_list and not res.get('trade_channel'):
                if session.current_trade_channel:
                    res['trade_channel'] = session.current_trade_channel
                elif session.config_id.default_trade_channel:
                    res['trade_channel'] = session.config_id.default_trade_channel
        return res

    def action_confirm(self):
        """ยืนยัน → จำค่าพนักงาน+ช่องทาง+trade channel ลง session → เปิดหน้าสร้าง order"""
        self.ensure_one()
        if not self.employee_id:
            raise UserError(_('กรุณาเลือกพนักงานขาย'))
        if self.session_id.state != 'opened':
            raise UserError(_('Session นี้ถูกปิดแล้ว'))

        # จำค่าลง session
        self.session_id.write({
            'current_employee_id': self.employee_id.id,
            'current_channel': self.channel,
            'current_trade_channel': self.trade_channel,
        })

        return self.session_id.action_new_order()
