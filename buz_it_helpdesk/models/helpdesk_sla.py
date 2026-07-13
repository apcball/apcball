from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HelpdeskSla(models.Model):
    _name = "it.helpdesk.sla"
    _description = "Helpdesk SLA"
    _check_company_auto = True
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    category_id = fields.Many2one("it.helpdesk.category", ondelete="cascade", check_company=True)
    priority_id = fields.Many2one("it.helpdesk.priority", ondelete="cascade", check_company=True)
    response_hours = fields.Float(default=4.0, required=True)
    resolution_hours = fields.Float(default=24.0, required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

    @api.constrains("response_hours", "resolution_hours")
    def _check_hours(self):
        for record in self:
            if record.response_hours < 0 or record.resolution_hours < 0:
                raise ValidationError("SLA hours cannot be negative.")
