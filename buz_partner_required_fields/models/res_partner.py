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
            'street': 'ที่อยู่ (บรรทัดที่ 1)',
            'street2': 'ที่อยู่ (บรรทัดที่ 2)',
            'city': 'เมือง/ตำบล',
            'state_id': 'จังหวัด',
            'zip': 'รหัสไปรษณีย์',
            'country_id': 'ประเทศ',
            'vat': 'เลขประจำตัวผู้เสียภาษีอากร',
            'phone': 'โทรศัพท์',
            'email': 'อีเมล',
            'branch': 'สาขา',
        }

        for field_name, field_label in required_field_map.items():
            field_value = vals.get(field_name)
            if not field_value:
                if field_name not in vals:
                    continue
                missing_fields.append(field_label)

        if missing_fields:
            raise ValidationError(
                f"บริษัท '{partner_name}' ต้องกรอกข้อมูลต่อไปนี้: {', '.join(missing_fields)}"
            )

        vat = vals.get('vat')
        if vat and not self._validate_vat_format(vat):
            raise ValidationError(
                f"เลขประจำตัวผู้เสียภาษีอากรของ '{partner_name}' ต้องเป็นตัวเลข 13 หลักพอดี (ปัจจุบัน: {vat})"
            )

    @staticmethod
    def _validate_vat_format(vat):
        if not vat:
            return True
        return vat.isdigit() and len(vat) == 13
