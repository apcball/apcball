from odoo import fields, models


class HelpdeskStage(models.Model):
    _name = "it.helpdesk.stage"
    _description = "Helpdesk Stage"
    _check_company_auto = True
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string="Fold in Kanban")
    is_closed = fields.Boolean(string="Closed Stage")
    description = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
