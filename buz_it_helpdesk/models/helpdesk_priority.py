from odoo import fields, models


class HelpdeskPriority(models.Model):
    _name = "it.helpdesk.priority"
    _description = "Helpdesk Priority"
    _check_company_auto = True
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    code = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
        required=True,
    )
    sequence = fields.Integer(default=10)
    color = fields.Integer(default=0)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    _sql_constraints = [("code_company_uniq", "unique(code, company_id)", "Priority must be unique per company.")]
