from odoo import fields, models


class HelpdeskCategory(models.Model):
    _name = "it.helpdesk.category"
    _description = "Helpdesk Category"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    description = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    _sql_constraints = [("name_company_uniq", "unique(name, company_id)", "Category must be unique per company.")]
