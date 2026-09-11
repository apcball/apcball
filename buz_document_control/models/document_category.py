from odoo import fields, models


class BuzDocumentCategory(models.Model):
    _name = "buz.document.category"
    _description = "ISO Document Category"
    _parent_store = True
    _parent_name = "parent_id"
    _order = "parent_path, name"

    name = fields.Char(required=True, translate=True)
    parent_id = fields.Many2one("buz.document.category", index=True, ondelete="restrict")
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("buz.document.category", "parent_id")
    active = fields.Boolean(default=True)
