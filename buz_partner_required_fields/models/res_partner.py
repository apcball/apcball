from odoo import api, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._validate_required_fields(vals)
        return super().create(vals_list)

    def write(self, vals):
        for partner in self:
            merged_vals = {**partner.read([], load=False)[0], **vals}
            self._validate_required_fields(merged_vals)
        return super().write(vals)

    def _validate_required_fields(self, vals):
        if self.env.user.has_group('buz_partner_required_fields.group_partner_required_fields_bypass'):
            return

        company_type = vals.get('company_type')
        if company_type is None:
            company_type = self.browse(vals.get('id')).company_type if vals.get('id') else 'person'
        if company_type not in ('company', 'person'):
            return

        if company_type == 'person':
            parent_id = vals.get('parent_id')
            if parent_id is None and vals.get('id'):
                parent_id = self.browse(vals.get('id')).parent_id.id
            if parent_id:
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
        if company_type != 'company':
            required_field_map = {
                k: v for k, v in required_field_map.items()
                if k not in ('branch', 'vat')
            }

        for field_name, field_label in required_field_map.items():
            if not vals.get(field_name):
                missing_fields.append(field_label)

        if missing_fields:
            partner_type_label = 'บริษัท' if company_type == 'company' else 'บุคคลธรรมดา'
            raise ValidationError(
                f"{partner_type_label} '{partner_name}' ต้องกรอกข้อมูลต่อไปนี้: {', '.join(missing_fields)}"
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
