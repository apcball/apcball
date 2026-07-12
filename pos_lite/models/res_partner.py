from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def pos_lite_create_customer(self, data, company_id):
        """Create a customer with tax-invoice details from the POS terminal.

        Whitelists fields explicitly; validates Thai VAT format and guards
        against duplicate VAT (+branch when l10n_th_partner is installed).
        Returns the created partner record.
        """
        name = (data.get('name') or '').strip()
        if not name:
            raise ValidationError('กรุณากรอกชื่อลูกค้า')

        vat = (data.get('vat') or '').strip()
        if vat and not (vat.isdigit() and len(vat) == 13):
            raise ValidationError('เลขประจำตัวผู้เสียภาษีต้องเป็นตัวเลข 13 หลัก')

        branch = (data.get('branch') or '').strip()
        has_branch_field = 'branch' in self._fields  # from l10n_th_partner

        if vat:
            dup_domain = [
                ('vat', '=', vat),
                ('company_id', 'in', [False, company_id]),
            ]
            if has_branch_field:
                dup_domain.append(('branch', '=', branch or False))
            dup = self.search(dup_domain, limit=1)
            if dup:
                raise ValidationError(
                    'เลขภาษีนี้มีลูกค้าอยู่แล้ว: %s' % dup.display_name)

        vals = {
            'name': name,
            'vat': vat or False,
            'phone': (data.get('phone') or '').strip() or False,
            'street': (data.get('street') or '').strip() or False,
            'city': (data.get('city') or '').strip() or False,
            'zip': (data.get('zip') or '').strip() or False,
            'customer_rank': 1,
            'company_id': company_id,
        }
        if has_branch_field and branch:
            vals['branch'] = branch
        return self.create(vals)

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
