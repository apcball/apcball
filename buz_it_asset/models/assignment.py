from odoo import fields, models, _
from odoo.exceptions import UserError


class ITAssetAssignment(models.Model):
    _name = 'buz.it.asset.assignment'
    _description = 'IT Asset Assignment History'
    _check_company_auto = True
    _order = 'assigned_date desc, id desc'

    asset_id = fields.Many2one(
        'buz.it.asset', required=True, ondelete='restrict', check_company=True,
        index=True,
    )
    employee_id = fields.Many2one(
        'hr.employee', required=True, ondelete='restrict', check_company=True,
    )
    assigned_date = fields.Date(required=True, default=fields.Date.context_today)
    returned_date = fields.Date(readonly=True)
    assigned_by_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user,
        readonly=True,
    )
    returned_by_id = fields.Many2one('res.users', readonly=True)
    location_id = fields.Many2one('buz.it.asset.location', check_company=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        readonly=True, index=True,
    )
    notes = fields.Text()

    def write(self, vals):
        allowed = {'returned_date', 'returned_by_id'}
        if set(vals) - allowed:
            raise UserError(_('Assignment history is append-only.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Assignment history cannot be deleted.'))
