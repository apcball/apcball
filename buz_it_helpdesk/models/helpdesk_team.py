from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HelpdeskTeam(models.Model):
    _name = "it.helpdesk.team"
    _description = "IT Helpdesk Team"
    _check_company_auto = True
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    member_ids = fields.Many2many("res.users", string="Team Members")
    category_ids = fields.Many2many("it.helpdesk.category", string="Categories")
    alias_id = fields.Many2one("mail.alias", string="Email Alias", ondelete="set null")
    active = fields.Boolean(default=True)

    @api.constrains("member_ids")
    def _check_members_company(self):
        for team in self:
            if any(team.company_id not in user.company_ids for user in team.member_ids):
                raise ValidationError("All team members must have access to the team company.")
