from odoo import fields, models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    default_allow_bill_bypass = fields.Boolean(
        string="Default Bill Before Receive",
        help="If checked, Purchase Orders for this vendor will by default allow billing before receipt."
    )
