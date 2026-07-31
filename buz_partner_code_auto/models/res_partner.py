from odoo import models, fields, api, _
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

    @api.constrains('partner_code', 'company_id')
    def _check_partner_code_unique(self):
        for record in self:
            if record.partner_code:
                domain = [
                    ('partner_code', '=ilike', record.partner_code),
                    ('id', '!=', record.id),
                ]
                if record.company_id:
                    domain += ['|', ('company_id', '=', False), ('company_id', '=', record.company_id.id)]
                existing = self.search(domain, limit=1)
                if existing:
                    raise ValidationError(_(
                        'Partner code "%(code)s" already exists for %(partner)s!',
                        code=record.partner_code, partner=existing.name,
                    ))
