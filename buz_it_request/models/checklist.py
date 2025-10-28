from odoo import models, fields


class ITAccessChecklist(models.Model):
    _name = 'it.access.checklist'
    _description = 'IT Access Request Checklist Item'

    request_id = fields.Many2one('it.request.access', string='Access Request', ondelete='cascade')
    name = fields.Char('Checklist Item', required=True)
    is_completed = fields.Boolean('Completed', default=False)
    notes = fields.Text('Notes')
    active = fields.Boolean(default=True)