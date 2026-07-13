from odoo import fields, models


class WebApiKeyShow(models.AbstractModel):
    _name = 'web.api.key.show'
    _description = 'Show Web API Key'

    integration_name = fields.Char(string='Integration', readonly=True)
    user_login = fields.Char(string='Odoo Login', readonly=True)
    key = fields.Char(string='API Key', readonly=True)
