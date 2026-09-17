from odoo import fields, models

from ..models.helpdesk_ticket import TICKET_REJECTION_REASON_TYPES


class HelpdeskTicketRejectWizard(models.TransientModel):
    _name = 'buz.helpdesk.ticket.reject.wizard'
    _description = 'Helpdesk Ticket Rejection'

    ticket_id = fields.Many2one(
        'buz.helpdesk.ticket', required=True, readonly=True,
    )
    reason_type = fields.Selection(
        TICKET_REJECTION_REASON_TYPES,
        string='Reason Type',
        required=True,
    )
    reason = fields.Text(string='Details', required=True)

    def action_confirm(self):
        self.ensure_one()
        self.ticket_id._reject_ticket(self.reason_type, self.reason)
        return {'type': 'ir.actions.act_window_close'}
