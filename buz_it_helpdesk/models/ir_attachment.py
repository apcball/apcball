from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    helpdesk_ticket_ids = fields.Many2many(
        'buz.helpdesk.ticket',
        'buz_helpdesk_ticket_attachment_rel',
        'attachment_id',
        'ticket_id',
        string='Helpdesk Tickets',
        readonly=True,
    )

    def _helpdesk_ticket_map(self):
        """อ่านความสัมพันธ์ย้อนกลับด้วย sudo แล้วตรวจสิทธิ์ภายหลัง"""
        if not self:
            return {}
        tickets = self.env['buz.helpdesk.ticket'].sudo().search([
            ('attachment_ids', 'in', self.ids),
        ])
        result = defaultdict(lambda: self.env['buz.helpdesk.ticket'])
        selected_ids = set(self.ids)
        for ticket in tickets:
            for attachment in ticket.attachment_ids:
                if attachment.id in selected_ids:
                    result[attachment.id] |= ticket
        return result

    def _helpdesk_allowed(self, operation):
        ticket_map = self._helpdesk_ticket_map()
        allowed = self.env['ir.attachment']
        for attachment in self:
            tickets = ticket_map.get(attachment.id)
            if not tickets:
                allowed |= attachment
                continue
            try:
                for ticket in tickets:
                    user_ticket = ticket.with_user(self.env.user)
                    if operation == 'read':
                        if not user_ticket._can_read_helpdesk_attachments():
                            raise AccessError(_('Attachment access is not allowed.'))
                    else:
                        if not user_ticket._can_manage_helpdesk_attachments():
                            raise AccessError(_('Attachment management is not allowed.'))
            except AccessError:
                continue
            allowed |= attachment
        return allowed

    def _filter_access_rules_python(self, operation):
        records = super()._filter_access_rules_python(operation)
        return records & records._helpdesk_allowed(operation)

    def check_access_rule(self, operation):
        result = super().check_access_rule(operation)
        forbidden = self - self._helpdesk_allowed(operation)
        if forbidden:
            raise AccessError(_(
                'You do not have permission to access this Helpdesk attachment.'
            ))
        return result

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('res_model') != 'buz.helpdesk.ticket' or not vals.get('res_id'):
                continue
            ticket = self.env['buz.helpdesk.ticket'].browse(vals['res_id']).exists()
            if ticket:
                ticket._check_helpdesk_attachment_write()
        return super().create(vals_list)

    def write(self, vals):
        allowed = self._helpdesk_allowed('write')
        if allowed != self:
            raise AccessError(_(
                'You do not have permission to edit this Helpdesk attachment.'
            ))
        return super().write(vals)

    def unlink(self):
        allowed = self._helpdesk_allowed('unlink')
        if allowed != self:
            raise AccessError(_(
                'You do not have permission to delete this Helpdesk attachment.'
            ))
        return super().unlink()
