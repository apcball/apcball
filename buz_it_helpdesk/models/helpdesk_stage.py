from odoo import api, fields, models
from odoo.exceptions import ValidationError


STAGE_CODES = {
    'draft': 'Draft',
    'new': 'New',
    'in_progress': 'In Progress',
    'pending_user': 'Pending User',
    'resolved': 'Resolved',
    'closed': 'Closed',
    'cancelled': 'Cancelled',
}


class HelpdeskStage(models.Model):
    _name = 'buz.helpdesk.stage'
    _description = 'Helpdesk Stage'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    code = fields.Char(
        string='Code',
        required=True,
        index=True,
        help='Technical code used for transition validation.',
    )
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string='Fold in Kanban')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'The stage name must be unique.'),
        ('code_uniq', 'unique(code)', 'The stage code must be unique.'),
    ]

    @api.constrains('code')
    def _check_code_valid(self):
        for stage in self:
            if stage.code and stage.code not in STAGE_CODES:
                raise ValidationError(
                    "Stage code must be one of: %s" % ', '.join(STAGE_CODES)
                )
