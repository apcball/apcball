from odoo import fields, models


class HelpdeskApprovalRejectWizard(models.TransientModel):
    _name = 'buz.helpdesk.approval.reject.wizard'
    _description = 'Helpdesk Approval Rejection'

    ticket_id = fields.Many2one(
        'buz.helpdesk.ticket', required=True, readonly=True,
    )
    reason = fields.Text(string='Rejection Reason', required=True)

    def action_confirm(self):
        self.ensure_one()
        self.ticket_id._reject_approval(self.reason)
        return {'type': 'ir.actions.act_window_close'}
