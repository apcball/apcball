from odoo import fields, models


class BuzDocumentType(models.Model):
    _name = "buz.document.type"
    _description = "ISO Document Type"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [("code_uniq", "unique(code)", "Document type code must be unique.")]
