from odoo import models


class HelpdeskLineComposer(models.TransientModel):
    _inherit = 'mail.compose.message'

    def action_send_mail(self):
        if not self.env.context.get('buz_helpdesk_line_contact'):
            return super().action_send_mail()
        self.ensure_one()
        ticket = self.env['buz.helpdesk.ticket'].browse(
            self.env.context.get('buz_helpdesk_ticket_id')
        ).exists()
        ticket.action_send_line_message(
            self.body,
            attachment_ids=self.attachment_ids.ids,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'LINE',
                'message': 'ส่ง LINE สำเร็จ',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
