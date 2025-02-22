from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    ref = fields.Char(string='Reference')
    vat = fields.Char(string='Tax ID')
    street = fields.Char(string='Street')
    street2 = fields.Char(string='Street2')
    city = fields.Char(string='City')
    state_id = fields.Many2one('res.country.state', string='State')
    zip = fields.Char(string='Zip')
    phone = fields.Char(string='Phone')
    fax = fields.Char(string='Fax')