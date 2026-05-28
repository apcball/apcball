from odoo import api, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not self.env.context.get('pos_lite_partner_search'):
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        args = list(args or [])
        name = (name or '').strip()
        if not name:
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        domain = [
            '|', '|', '|',
            ('name', operator, name),
            ('phone', '=', name),
            ('mobile', '=', name),
            ('vat', '=', name),
        ]
        partners = self.search(domain + args, limit=limit)
        if partners:
            return [(p.id, p.display_name) for p in partners]
        return super().name_search(name=name, args=args, operator=operator, limit=limit)
