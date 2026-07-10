from odoo import fields, models


class HelpdeskTag(models.Model):
    _name = "it.helpdesk.tag"
    _description = "Helpdesk Tag"
    _order = "name"

    name = fields.Char(required=True)
    color = fields.Integer(default=0)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    _sql_constraints = [("name_company_uniq", "unique(name, company_id)", "Tag must be unique per company.")]
