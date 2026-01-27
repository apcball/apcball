from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    partner_code = fields.Char(
        string='Partner Code',
        help='Unique code for this partner',
        index=True,
        copy=False,
        size=50
    )

    @api.constrains('partner_code')
    def _check_partner_code_unique(self):
        for record in self:
            if record.partner_code:
                existing = self.search([
                    ('partner_code', '=', record.partner_code),
                    ('id', '!=', record.id)
                ])
                if existing:
                    raise ValidationError(f'Partner code "{record.partner_code}" already exists for {existing.name}!')
