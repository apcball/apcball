from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    partner_code = fields.Char(string='Partner Code')
    old_code_partner =  fields.Char(string='Old Code Partner')
    office = fields.Char(string='Office')
    partner_group = fields.Char(string='Partner_Group')
    partner_type = fields.Char(string='Partner_Type')
