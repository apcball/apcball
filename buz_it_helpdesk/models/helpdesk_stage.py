from odoo import fields, models, _
from odoo.exceptions import UserError


class HelpdeskStage(models.Model):
    _name = 'buz.helpdesk.stage'
    _description = 'Helpdesk Stage'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string='Fold in Kanban')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'The stage name must be unique.'),
    ]

    def _protected_stage_ids(self):
        return {
            self.env.ref('buz_it_helpdesk.stage_draft').id,
            self.env.ref('buz_it_helpdesk.stage_new').id,
            self.env.ref('buz_it_helpdesk.stage_in_progress').id,
            self.env.ref('buz_it_helpdesk.stage_resolved').id,
            self.env.ref('buz_it_helpdesk.stage_closed').id,
        }

    def write(self, vals):
        if vals.get('active') is False:
            protected = self._protected_stage_ids()
            if protected.intersection(self.ids):
                raise UserError(_('Workflow stages cannot be archived.'))
        return super().write(vals)

    def unlink(self):
        if self._protected_stage_ids().intersection(self.ids):
            raise UserError(_('Workflow stages cannot be deleted.'))
        ticket_count = self.env['buz.helpdesk.ticket'].search_count([
            ('stage_id', 'in', self.ids),
        ])
        if ticket_count:
            raise UserError(_(
                'A stage used by tickets cannot be deleted. Move the tickets '
                'to another stage first.'
            ))
        return super().unlink()
