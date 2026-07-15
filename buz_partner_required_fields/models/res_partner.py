from odoo import api, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._validate_required_fields_for_company(vals)
        return super().create(vals_list)

    def write(self, vals):
        for partner in self:
            merged_vals = {**partner.read([], load=False)[0], **vals}
            self._validate_required_fields_for_company(merged_vals)
        return super().write(vals)

    def _validate_required_fields_for_company(self, vals):
        company_type = vals.get('company_type')
        if company_type is None:
            company_type = self.browse(vals.get('id')).company_type if vals.get('id') else 'person'
        if company_type != 'company':
            return

        partner_name = vals.get('name', 'Partner')
        missing_fields = []

        required_field_map = {
            'street': 'Address (Line 1)',
            'street2': 'Address (Line 2)',
            'city': 'City',
            'state_id': 'State',
            'zip': 'Zip Code',
            'country_id': 'Country',
            'vat': 'Tax ID',
            'phone': 'Phone',
            'email': 'Email',
            'branch': 'Tax Branch',
        }

        for field_name, field_label in required_field_map.items():
            field_value = vals.get(field_name)
            if not field_value:
                if field_name not in vals:
                    continue
                missing_fields.append(field_label)

        if missing_fields:
            raise ValidationError(
                f"Company partner '{partner_name}' missing required fields: {', '.join(missing_fields)}"
            )

        vat = vals.get('vat')
        if vat and not self._validate_vat_format(vat):
            raise ValidationError(
                f"Tax ID for '{partner_name}' must be exactly 13 digits (current: {vat})"
            )

    @staticmethod
    def _validate_vat_format(vat):
        if not vat:
            return True
        return vat.isdigit() and len(vat) == 13
