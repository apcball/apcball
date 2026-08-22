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
        ticket.action_send_line_message(self.body)
        return {'type': 'ir.actions.act_window_close'}
