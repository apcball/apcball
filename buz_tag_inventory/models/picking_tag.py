from odoo import fields, models


class BuzPickingTag(models.Model):
    _name = "buz.picking.tag"
    _description = "Picking Tag"

    name = fields.Char(required=True)
    color = fields.Integer(string="Color Index", default=0)
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company
    )

    _sql_constraints = [
        ("name_uniq", "unique(name, company_id)", "Tag name must be unique."),
    ]
