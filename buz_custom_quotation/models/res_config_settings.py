from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sale_header_name = fields.Char(
        string='Sale Header Name',
        config_parameter='buz_custom_quotation.sale_header_name'
    )