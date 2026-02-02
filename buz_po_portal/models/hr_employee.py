from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    signature_image = fields.Binary(string="Signature Image", attachment=True)
