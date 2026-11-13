from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


DATA_FIELDS = (
    'company_name', 'registration_number', 'certificate_number', 'issue_date',
    'shareholder_name', 'share_count', 'share_number_from', 'share_number_to',
    'registered_capital', 'total_shares', 'share_value', 'paid_per_share', 'total_paid',
    'previous_certificate_number', 'previous_certificate_date', 'receipt_date',
    'director_one', 'director_two',
)


LAYOUT_DEFAULTS = {
    'page_offset_x_mm': 0.0,
    'page_offset_y_mm': 0.0,
    'stub_width_mm': 91.5,
    'body_font_size_pt': 10.0,
    'company_font_size_pt': 14.0,
    'stub_header_top_mm': 24.0,
    'stub_registration_top_mm': 33.0,
    'stub_certificate_top_mm': 42.0,
    'stub_shareholder_top_mm': 50.0,
    'stub_share_count_top_mm': 58.0,
    'stub_share_range_top_mm': 66.0,
    'stub_paid_top_mm': 78.0,
    'stub_total_paid_top_mm': 86.0,
    'stub_cancellation_top_mm': 99.0,
    'stub_receipt_top_mm': 168.0,
    'certificate_number_top_mm': 16.0,
    'certificate_company_top_mm': 33.0,
    'certificate_registration_top_mm': 47.0,
    'certificate_capital_top_mm': 66.0,
    'certificate_shareholder_top_mm': 78.0,
    'certificate_share_count_top_mm': 109.0,
    'certificate_paid_top_mm': 132.0,
    'certificate_issue_date_top_mm': 145.0,
    'certificate_directors_top_mm': 171.0,
}


class ShareCertificateData(models.AbstractModel):
    _name = 'buz.share.certificate.data'
    _description = 'Share Certificate Fields'

    company_name = fields.Char(string='ชื่อบริษัท')
    registration_number = fields.Char(string='ทะเบียนเลขที่')
    certificate_number = fields.Char(string='ใบหุ้นเลขที่')
    issue_date = fields.Date(string='วันที่ออกใบหุ้น')
    shareholder_name = fields.Char(string='ชื่อผู้ถือหุ้น')
    share_count = fields.Integer(string='จำนวนหุ้นที่ถือ')
    share_number_from = fields.Char(string='หมายเลขหุ้นตั้งแต่')
    share_number_to = fields.Char(string='หมายเลขหุ้นถึง')
    registered_capital = fields.Float(string='ทุนจดทะเบียน', digits=(16, 2))
    total_shares = fields.Integer(string='จำนวนหุ้นทั้งหมด')
    share_value = fields.Float(string='มูลค่าหุ้นละ', digits=(16, 2))
    paid_per_share = fields.Float(string='ชำระแล้วหุ้นละ', digits=(16, 2))
    total_paid = fields.Float(string='รวมเงินค่าหุ้นที่ชำระแล้ว', digits=(16, 2))
    previous_certificate_number = fields.Char(string='ยกเลิกใบหุ้นเดิมเลขที่')
    previous_certificate_date = fields.Date(string='วันที่ใบหุ้นเดิม')
    receipt_date = fields.Date(string='วันที่รับใบหุ้น')
    director_one = fields.Char(string='ชื่อกรรมการคนที่ 1')
    director_two = fields.Char(string='ชื่อกรรมการคนที่ 2')

    def thai_date(self, value):
        if not value:
            return ''
        months = ('มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
                  'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม')
        return '%s %s %s' % (value.day, months[value.month - 1], value.year + 543)


class ShareCertificateTemplate(models.Model):
    _name = 'buz.share.certificate.template'
    _inherit = 'buz.share.certificate.data'
    _description = 'Share Certificate Template'
    _order = 'name, id'

    name = fields.Char(string='ชื่อ Template', required=True)
    user_id = fields.Many2one('res.users', string='ผู้สร้าง', required=True,
                              default=lambda self: self.env.user, readonly=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values['user_id'] = self.env.uid
        return super().create(vals_list)

    def write(self, values):
        if 'user_id' in values and any(record.user_id.id != values['user_id'] for record in self):
            raise AccessError(_('ไม่สามารถเปลี่ยนเจ้าของ Template ได้'))
        return super().write(values)

    def action_use_template(self):
        self.ensure_one()
        values = {name: self[name] for name in DATA_FIELDS}
        values['template_id'] = self.id
        certificate = self.env['buz.share.certificate'].create(values)
        return {
            'type': 'ir.actions.act_window', 'name': _('ใบหุ้น'),
            'res_model': certificate._name, 'res_id': certificate.id,
            'view_mode': 'form', 'view_id': self.env.ref(
                'buz_share_certificate.view_share_certificate_form'
            ).id,
            'target': 'current',
        }


class ShareCertificate(models.Model):
    _name = 'buz.share.certificate'
    _inherit = 'buz.share.certificate.data'
    _description = 'Share Certificate'
    _rec_name = 'certificate_number'
    _order = 'id desc'

    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')],
                             default='draft', required=True, readonly=True)
    user_id = fields.Many2one('res.users', string='ผู้สร้าง', required=True,
                              default=lambda self: self.env.user, readonly=True, index=True)
    template_id = fields.Many2one('buz.share.certificate.template', string='Template',
                                  domain=lambda self: [('user_id', '=', self.env.uid)])
    template_name = fields.Char(string='ชื่อ Template')

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values['user_id'] = self.env.uid
            values['state'] = 'draft'
        return super().create(vals_list)

    def write(self, values):
        if 'user_id' in values and any(record.user_id.id != values['user_id'] for record in self):
            raise AccessError(_('ไม่สามารถเปลี่ยนเจ้าของใบหุ้นได้'))
        if any(record.state == 'done' for record in self) and values != {'state': 'draft'}:
            raise UserError(_('กรุณา Reset to Draft ก่อนแก้ไขใบหุ้น'))
        return super().write(values)

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def action_print_options(self):
        self.ensure_one()
        wizard = self.env['buz.share.certificate.wizard'].create({'certificate_id': self.id})
        return {
            'type': 'ir.actions.act_window', 'name': _('What do you want to do?'),
            'res_model': wizard._name, 'res_id': wizard.id, 'view_mode': 'form',
            'view_id': self.env.ref('buz_share_certificate.view_share_certificate_print_options').id,
            'context': dict(self.env.context, dialog_size='small'),
            'target': 'new',
        }


class ShareCertificateLayoutConfig(models.Model):
    _name = 'buz.share.certificate.layout.config'
    _description = 'Share Certificate Print Layout Configuration'
    _rec_name = 'name'

    name = fields.Char(string='ชื่อ Configuration', required=True, default='ค่าเริ่มต้น')
    page_offset_x_mm = fields.Float(string='ชดเชยแนวนอน (mm)', default=LAYOUT_DEFAULTS['page_offset_x_mm'])
    page_offset_y_mm = fields.Float(string='ชดเชยแนวตั้ง (mm)', default=LAYOUT_DEFAULTS['page_offset_y_mm'])
    stub_width_mm = fields.Float(string='ความกว้างต้นขั้ว (mm)', default=LAYOUT_DEFAULTS['stub_width_mm'])
    body_font_size_pt = fields.Float(string='ขนาดตัวอักษรข้อมูล (pt)', default=LAYOUT_DEFAULTS['body_font_size_pt'])
    company_font_size_pt = fields.Float(string='ขนาดชื่อบริษัท (pt)', default=LAYOUT_DEFAULTS['company_font_size_pt'])

    stub_header_top_mm = fields.Float(string='ข้อมูลบริษัท (mm)', default=LAYOUT_DEFAULTS['stub_header_top_mm'])
    stub_registration_top_mm = fields.Float(string='ทะเบียนเลขที่ (mm)', default=LAYOUT_DEFAULTS['stub_registration_top_mm'])
    stub_certificate_top_mm = fields.Float(string='เลขที่และวันที่ใบหุ้น (mm)', default=LAYOUT_DEFAULTS['stub_certificate_top_mm'])
    stub_shareholder_top_mm = fields.Float(string='ชื่อผู้ถือหุ้น (mm)', default=LAYOUT_DEFAULTS['stub_shareholder_top_mm'])
    stub_share_count_top_mm = fields.Float(string='จำนวนหุ้น (mm)', default=LAYOUT_DEFAULTS['stub_share_count_top_mm'])
    stub_share_range_top_mm = fields.Float(string='ช่วงเลขหุ้น (mm)', default=LAYOUT_DEFAULTS['stub_share_range_top_mm'])
    stub_paid_top_mm = fields.Float(string='ชำระแล้วต่อหุ้น (mm)', default=LAYOUT_DEFAULTS['stub_paid_top_mm'])
    stub_total_paid_top_mm = fields.Float(string='รวมชำระแล้ว (mm)', default=LAYOUT_DEFAULTS['stub_total_paid_top_mm'])
    stub_cancellation_top_mm = fields.Float(string='ใบหุ้นเดิมที่ยกเลิก (mm)', default=LAYOUT_DEFAULTS['stub_cancellation_top_mm'])
    stub_receipt_top_mm = fields.Float(string='วันที่รับใบหุ้น (mm)', default=LAYOUT_DEFAULTS['stub_receipt_top_mm'])

    certificate_number_top_mm = fields.Float(string='เลขที่ใบหุ้น (mm)', default=LAYOUT_DEFAULTS['certificate_number_top_mm'])
    certificate_company_top_mm = fields.Float(string='ชื่อบริษัท (mm)', default=LAYOUT_DEFAULTS['certificate_company_top_mm'])
    certificate_registration_top_mm = fields.Float(string='ทะเบียนเลขที่ใบหุ้น (mm)', default=LAYOUT_DEFAULTS['certificate_registration_top_mm'])
    certificate_capital_top_mm = fields.Float(string='ข้อมูลทุนและมูลค่าหุ้น (mm)', default=LAYOUT_DEFAULTS['certificate_capital_top_mm'])
    certificate_shareholder_top_mm = fields.Float(string='ชื่อผู้ถือหุ้นใบหุ้น (mm)', default=LAYOUT_DEFAULTS['certificate_shareholder_top_mm'])
    certificate_share_count_top_mm = fields.Float(string='จำนวนและเลขหุ้น (mm)', default=LAYOUT_DEFAULTS['certificate_share_count_top_mm'])
    certificate_paid_top_mm = fields.Float(string='ข้อมูลการชำระค่าหุ้น (mm)', default=LAYOUT_DEFAULTS['certificate_paid_top_mm'])
    certificate_issue_date_top_mm = fields.Float(string='วันที่ออกใบหุ้น (mm)', default=LAYOUT_DEFAULTS['certificate_issue_date_top_mm'])
    certificate_directors_top_mm = fields.Float(string='ชื่อกรรมการ (mm)', default=LAYOUT_DEFAULTS['certificate_directors_top_mm'])

    @api.model
    def get_default_config(self):
        return self.env.ref('buz_share_certificate.share_certificate_layout_config_default')

    def action_reset_defaults(self):
        self.ensure_one()
        self.write(LAYOUT_DEFAULTS)
        return True

    def action_preview_layout(self):
        self.ensure_one()
        return self.env.ref(
            'buz_share_certificate.action_report_share_certificate_preview'
        ).report_action(self, config=False)

    @api.constrains(
        'page_offset_x_mm', 'page_offset_y_mm', 'stub_width_mm',
        'body_font_size_pt', 'company_font_size_pt',
        'stub_header_top_mm', 'stub_registration_top_mm',
        'stub_certificate_top_mm', 'stub_shareholder_top_mm',
        'stub_share_count_top_mm', 'stub_share_range_top_mm',
        'stub_paid_top_mm', 'stub_total_paid_top_mm',
        'stub_cancellation_top_mm', 'stub_receipt_top_mm',
        'certificate_number_top_mm', 'certificate_company_top_mm',
        'certificate_registration_top_mm', 'certificate_capital_top_mm',
        'certificate_shareholder_top_mm', 'certificate_share_count_top_mm',
        'certificate_paid_top_mm', 'certificate_issue_date_top_mm',
        'certificate_directors_top_mm',
    )
    def _check_layout_bounds(self):
        position_fields = [name for name in LAYOUT_DEFAULTS if name.endswith('_top_mm')]
        for record in self:
            if not 70 <= record.stub_width_mm <= 120:
                raise ValidationError(_('ความกว้างต้นขั้วต้องอยู่ระหว่าง 70-120 mm'))
            if not -25 <= record.page_offset_x_mm <= 25 or not -25 <= record.page_offset_y_mm <= 25:
                raise ValidationError(_('ค่าชดเชยตำแหน่งต้องอยู่ระหว่าง -25 ถึง 25 mm'))
            if not 6 <= record.body_font_size_pt <= 24 or not 6 <= record.company_font_size_pt <= 30:
                raise ValidationError(_('ขนาดตัวอักษรอยู่นอกช่วงที่รองรับ'))
            if any(not 0 <= getattr(record, name) <= 210 for name in position_fields):
                raise ValidationError(_('ตำแหน่งแนวตั้งต้องอยู่ภายในกระดาษ A4 แนวนอน'))
