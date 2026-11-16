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
    'margin_top_mm': 0.0,
    'margin_bottom_mm': 0.0,
    'margin_left_mm': 0.0,
    'margin_right_mm': 0.0,
    'font_family': 'Sarabun',
    'stub_width_mm': 91.5,
}

POSITION_DEFAULTS = {
    'stub_company': (22.0, 24.0),
    'stub_registration': (33.0, 33.0),
    'stub_certificate_number': (26.0, 42.0),
    'stub_issue_date': (62.0, 42.0),
    'stub_shareholder': (31.0, 50.0),
    'stub_share_count': (49.0, 58.0),
    'stub_share_number_from': (39.0, 66.0),
    'stub_share_number_to': (67.0, 66.0),
    'stub_paid_per_share': (52.0, 78.0),
    'stub_total_paid': (48.0, 86.0),
    'stub_previous_certificate_number': (37.0, 99.0),
    'stub_previous_certificate_date': (65.0, 99.0),
    'stub_receipt_date': (31.0, 168.0),
    'certificate_number': (239.5, 16.0),
    'certificate_company': (139.5, 33.0),
    'certificate_registration': (153.5, 47.0),
    'certificate_registered_capital': (109.5, 66.0),
    'certificate_total_shares': (177.5, 66.0),
    'certificate_share_value': (244.5, 66.0),
    'certificate_shareholder': (120.5, 78.0),
    'certificate_share_count': (128.5, 109.0),
    'certificate_share_number_from': (191.5, 109.0),
    'certificate_share_number_to': (260.5, 109.0),
    'certificate_paid_per_share': (144.5, 132.0),
    'certificate_total_paid': (246.5, 132.0),
    'certificate_issue_day': (144.5, 145.0),
    'certificate_issue_month': (199.5, 145.0),
    'certificate_issue_year': (269.5, 145.0),
    'certificate_director_one': (152.5, 171.0),
    'certificate_director_two': (230.5, 171.0),
}
for _position, (_x, _y_field) in POSITION_DEFAULTS.items():
    LAYOUT_DEFAULTS[_position + '_x_mm'] = _x
    LAYOUT_DEFAULTS[_position + '_y_mm'] = _y_field
    LAYOUT_DEFAULTS[_position + '_font_size_pt'] = 14.0 if _position == 'certificate_company' else 10.0
POSITION_FIELDS = tuple(
    name + axis + '_mm'
    for name in POSITION_DEFAULTS
    for axis in ('_x', '_y')
)
FONT_SIZE_FIELDS = tuple(name + '_font_size_pt' for name in POSITION_DEFAULTS)
POSITION_WIDTHS = {
    'stub_company': 64, 'stub_registration': 53, 'stub_certificate_number': 32,
    'stub_issue_date': 26, 'stub_shareholder': 55, 'stub_share_count': 17,
    'stub_share_number_from': 19, 'stub_share_number_to': 18, 'stub_paid_per_share': 25,
    'stub_total_paid': 32, 'stub_previous_certificate_number': 25,
    'stub_previous_certificate_date': 25, 'stub_receipt_date': 53,
    'certificate_number': 42, 'certificate_company': 112, 'certificate_registration': 88,
    'certificate_registered_capital': 47, 'certificate_total_shares': 32,
    'certificate_share_value': 35, 'certificate_shareholder': 155,
    'certificate_share_count': 22, 'certificate_share_number_from': 21,
    'certificate_share_number_to': 21, 'certificate_paid_per_share': 30,
    'certificate_total_paid': 38, 'certificate_issue_day': 15,
    'certificate_issue_month': 42, 'certificate_issue_year': 28,
    'certificate_director_one': 63, 'certificate_director_two': 63,
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
    total_paid = fields.Float(
        string='รวมเงินค่าหุ้นที่ชำระแล้ว', compute='_compute_total_paid',
        store=True, readonly=True, digits=(16, 2),
    )
    previous_certificate_number = fields.Char(string='ยกเลิกใบหุ้นเดิมเลขที่')
    previous_certificate_date = fields.Date(string='วันที่ใบหุ้นเดิม')
    receipt_date = fields.Date(string='วันที่รับใบหุ้น')
    director_one = fields.Char(string='ชื่อกรรมการคนที่ 1')
    director_two = fields.Char(string='ชื่อกรรมการคนที่ 2')

    @api.depends('share_count', 'paid_per_share')
    def _compute_total_paid(self):
        for record in self:
            record.total_paid = record.share_count * record.paid_per_share

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
    margin_top_mm = fields.Float(string='ขอบบน (mm)', default=0.0)
    margin_bottom_mm = fields.Float(string='ขอบล่าง (mm)', default=0.0)
    margin_left_mm = fields.Float(string='ขอบซ้าย (mm)', default=0.0)
    margin_right_mm = fields.Float(string='ขอบขวา (mm)', default=0.0)
    font_family = fields.Selection([('Sarabun', 'Sarabun')], string='Font', default='Sarabun', required=True)
    stub_width_mm = fields.Float(string='ความกว้างต้นขั้ว (mm)', default=LAYOUT_DEFAULTS['stub_width_mm'])

    stub_company_x_mm = fields.Float(string='ต้นขั้ว ชื่อบริษัท แนวนอน (mm)', default=22.0)
    stub_company_y_mm = fields.Float(string='ต้นขั้ว ชื่อบริษัท แนวตั้ง (mm)', default=24.0)
    stub_registration_x_mm = fields.Float(string='ต้นขั้ว ทะเบียนเลขที่ แนวนอน (mm)', default=33.0)
    stub_registration_y_mm = fields.Float(string='ต้นขั้ว ทะเบียนเลขที่ แนวตั้ง (mm)', default=33.0)
    stub_certificate_number_x_mm = fields.Float(string='ต้นขั้ว เลขที่ใบหุ้น แนวนอน (mm)', default=26.0)
    stub_certificate_number_y_mm = fields.Float(string='ต้นขั้ว เลขที่ใบหุ้น แนวตั้ง (mm)', default=42.0)
    stub_issue_date_x_mm = fields.Float(string='ต้นขั้ว วันที่ใบหุ้น แนวนอน (mm)', default=62.0)
    stub_issue_date_y_mm = fields.Float(string='ต้นขั้ว วันที่ใบหุ้น แนวตั้ง (mm)', default=42.0)
    stub_shareholder_x_mm = fields.Float(string='ต้นขั้ว ชื่อผู้ถือหุ้น แนวนอน (mm)', default=31.0)
    stub_shareholder_y_mm = fields.Float(string='ต้นขั้ว ชื่อผู้ถือหุ้น แนวตั้ง (mm)', default=50.0)
    stub_share_count_x_mm = fields.Float(string='ต้นขั้ว จำนวนหุ้น แนวนอน (mm)', default=49.0)
    stub_share_count_y_mm = fields.Float(string='ต้นขั้ว จำนวนหุ้น แนวตั้ง (mm)', default=58.0)
    stub_share_number_from_x_mm = fields.Float(string='ต้นขั้ว หุ้นเริ่มต้น แนวนอน (mm)', default=39.0)
    stub_share_number_from_y_mm = fields.Float(string='ต้นขั้ว หุ้นเริ่มต้น แนวตั้ง (mm)', default=66.0)
    stub_share_number_to_x_mm = fields.Float(string='ต้นขั้ว หุ้นสุดท้าย แนวนอน (mm)', default=67.0)
    stub_share_number_to_y_mm = fields.Float(string='ต้นขั้ว หุ้นสุดท้าย แนวตั้ง (mm)', default=66.0)
    stub_paid_per_share_x_mm = fields.Float(string='ต้นขั้ว ชำระต่อหุ้น แนวนอน (mm)', default=52.0)
    stub_paid_per_share_y_mm = fields.Float(string='ต้นขั้ว ชำระต่อหุ้น แนวตั้ง (mm)', default=78.0)
    stub_total_paid_x_mm = fields.Float(string='ต้นขั้ว รวมชำระแล้ว แนวนอน (mm)', default=48.0)
    stub_total_paid_y_mm = fields.Float(string='ต้นขั้ว รวมชำระแล้ว แนวตั้ง (mm)', default=86.0)
    stub_previous_certificate_number_x_mm = fields.Float(string='ต้นขั้ว เลขที่ใบหุ้นเดิม แนวนอน (mm)', default=37.0)
    stub_previous_certificate_number_y_mm = fields.Float(string='ต้นขั้ว เลขที่ใบหุ้นเดิม แนวตั้ง (mm)', default=99.0)
    stub_previous_certificate_date_x_mm = fields.Float(string='ต้นขั้ว วันที่ใบหุ้นเดิม แนวนอน (mm)', default=65.0)
    stub_previous_certificate_date_y_mm = fields.Float(string='ต้นขั้ว วันที่ใบหุ้นเดิม แนวตั้ง (mm)', default=99.0)
    stub_receipt_date_x_mm = fields.Float(string='ต้นขั้ว วันที่รับใบหุ้น แนวนอน (mm)', default=31.0)
    stub_receipt_date_y_mm = fields.Float(string='ต้นขั้ว วันที่รับใบหุ้น แนวตั้ง (mm)', default=168.0)

    certificate_number_x_mm = fields.Float(string='ใบหุ้น เลขที่ใบหุ้น แนวนอน (mm)', default=239.5)
    certificate_number_y_mm = fields.Float(string='ใบหุ้น เลขที่ใบหุ้น แนวตั้ง (mm)', default=16.0)
    certificate_company_x_mm = fields.Float(string='ใบหุ้น ชื่อบริษัท แนวนอน (mm)', default=139.5)
    certificate_company_y_mm = fields.Float(string='ใบหุ้น ชื่อบริษัท แนวตั้ง (mm)', default=33.0)
    certificate_registration_x_mm = fields.Float(string='ใบหุ้น ทะเบียนเลขที่ แนวนอน (mm)', default=153.5)
    certificate_registration_y_mm = fields.Float(string='ใบหุ้น ทะเบียนเลขที่ แนวตั้ง (mm)', default=47.0)
    certificate_registered_capital_x_mm = fields.Float(string='ใบหุ้น ทุนจดทะเบียน แนวนอน (mm)', default=109.5)
    certificate_registered_capital_y_mm = fields.Float(string='ใบหุ้น ทุนจดทะเบียน แนวตั้ง (mm)', default=66.0)
    certificate_total_shares_x_mm = fields.Float(string='ใบหุ้น จำนวนหุ้นทั้งหมด แนวนอน (mm)', default=177.5)
    certificate_total_shares_y_mm = fields.Float(string='ใบหุ้น จำนวนหุ้นทั้งหมด แนวตั้ง (mm)', default=66.0)
    certificate_share_value_x_mm = fields.Float(string='ใบหุ้น มูลค่าหุ้น แนวนอน (mm)', default=244.5)
    certificate_share_value_y_mm = fields.Float(string='ใบหุ้น มูลค่าหุ้น แนวตั้ง (mm)', default=66.0)
    certificate_shareholder_x_mm = fields.Float(string='ใบหุ้น ชื่อผู้ถือหุ้น แนวนอน (mm)', default=120.5)
    certificate_shareholder_y_mm = fields.Float(string='ใบหุ้น ชื่อผู้ถือหุ้น แนวตั้ง (mm)', default=78.0)
    certificate_share_count_x_mm = fields.Float(string='ใบหุ้น จำนวนหุ้น แนวนอน (mm)', default=128.5)
    certificate_share_count_y_mm = fields.Float(string='ใบหุ้น จำนวนหุ้น แนวตั้ง (mm)', default=109.0)
    certificate_share_number_from_x_mm = fields.Float(string='ใบหุ้น หุ้นเริ่มต้น แนวนอน (mm)', default=191.5)
    certificate_share_number_from_y_mm = fields.Float(string='ใบหุ้น หุ้นเริ่มต้น แนวตั้ง (mm)', default=109.0)
    certificate_share_number_to_x_mm = fields.Float(string='ใบหุ้น หุ้นสุดท้าย แนวนอน (mm)', default=260.5)
    certificate_share_number_to_y_mm = fields.Float(string='ใบหุ้น หุ้นสุดท้าย แนวตั้ง (mm)', default=109.0)
    certificate_paid_per_share_x_mm = fields.Float(string='ใบหุ้น ชำระต่อหุ้น แนวนอน (mm)', default=144.5)
    certificate_paid_per_share_y_mm = fields.Float(string='ใบหุ้น ชำระต่อหุ้น แนวตั้ง (mm)', default=132.0)
    certificate_total_paid_x_mm = fields.Float(string='ใบหุ้น รวมชำระแล้ว แนวนอน (mm)', default=246.5)
    certificate_total_paid_y_mm = fields.Float(string='ใบหุ้น รวมชำระแล้ว แนวตั้ง (mm)', default=132.0)
    certificate_issue_day_x_mm = fields.Float(string='ใบหุ้น วันออกใบหุ้น แนวนอน (mm)', default=144.5)
    certificate_issue_day_y_mm = fields.Float(string='ใบหุ้น วันออกใบหุ้น แนวตั้ง (mm)', default=145.0)
    certificate_issue_month_x_mm = fields.Float(string='ใบหุ้น เดือนออกใบหุ้น แนวนอน (mm)', default=199.5)
    certificate_issue_month_y_mm = fields.Float(string='ใบหุ้น เดือนออกใบหุ้น แนวตั้ง (mm)', default=145.0)
    certificate_issue_year_x_mm = fields.Float(string='ใบหุ้น ปีออกใบหุ้น แนวนอน (mm)', default=269.5)
    certificate_issue_year_y_mm = fields.Float(string='ใบหุ้น ปีออกใบหุ้น แนวตั้ง (mm)', default=145.0)
    certificate_director_one_x_mm = fields.Float(string='ใบหุ้น กรรมการ 1 แนวนอน (mm)', default=152.5)
    certificate_director_one_y_mm = fields.Float(string='ใบหุ้น กรรมการ 1 แนวตั้ง (mm)', default=171.0)
    certificate_director_two_x_mm = fields.Float(string='ใบหุ้น กรรมการ 2 แนวนอน (mm)', default=230.5)
    certificate_director_two_y_mm = fields.Float(string='ใบหุ้น กรรมการ 2 แนวตั้ง (mm)', default=171.0)

    stub_company_font_size_pt = fields.Float(string='ต้นขั้ว ชื่อบริษัท (pt)', default=10.0)
    stub_registration_font_size_pt = fields.Float(string='ต้นขั้ว ทะเบียนเลขที่ (pt)', default=10.0)
    stub_certificate_number_font_size_pt = fields.Float(string='ต้นขั้ว เลขที่ใบหุ้น (pt)', default=10.0)
    stub_issue_date_font_size_pt = fields.Float(string='ต้นขั้ว วันที่ใบหุ้น (pt)', default=10.0)
    stub_shareholder_font_size_pt = fields.Float(string='ต้นขั้ว ชื่อผู้ถือหุ้น (pt)', default=10.0)
    stub_share_count_font_size_pt = fields.Float(string='ต้นขั้ว จำนวนหุ้น (pt)', default=10.0)
    stub_share_number_from_font_size_pt = fields.Float(string='ต้นขั้ว หุ้นเริ่มต้น (pt)', default=10.0)
    stub_share_number_to_font_size_pt = fields.Float(string='ต้นขั้ว หุ้นสุดท้าย (pt)', default=10.0)
    stub_paid_per_share_font_size_pt = fields.Float(string='ต้นขั้ว ชำระต่อหุ้น (pt)', default=10.0)
    stub_total_paid_font_size_pt = fields.Float(string='ต้นขั้ว รวมชำระแล้ว (pt)', default=10.0)
    stub_previous_certificate_number_font_size_pt = fields.Float(string='ต้นขั้ว เลขที่ใบหุ้นเดิม (pt)', default=10.0)
    stub_previous_certificate_date_font_size_pt = fields.Float(string='ต้นขั้ว วันที่ใบหุ้นเดิม (pt)', default=10.0)
    stub_receipt_date_font_size_pt = fields.Float(string='ต้นขั้ว วันที่รับใบหุ้น (pt)', default=10.0)
    certificate_number_font_size_pt = fields.Float(string='ใบหุ้น เลขที่ใบหุ้น (pt)', default=10.0)
    certificate_company_font_size_pt = fields.Float(string='ใบหุ้น ชื่อบริษัท (pt)', default=14.0)
    certificate_registration_font_size_pt = fields.Float(string='ใบหุ้น ทะเบียนเลขที่ (pt)', default=10.0)
    certificate_registered_capital_font_size_pt = fields.Float(string='ใบหุ้น ทุนจดทะเบียน (pt)', default=10.0)
    certificate_total_shares_font_size_pt = fields.Float(string='ใบหุ้น จำนวนหุ้นทั้งหมด (pt)', default=10.0)
    certificate_share_value_font_size_pt = fields.Float(string='ใบหุ้น มูลค่าหุ้น (pt)', default=10.0)
    certificate_shareholder_font_size_pt = fields.Float(string='ใบหุ้น ชื่อผู้ถือหุ้น (pt)', default=10.0)
    certificate_share_count_font_size_pt = fields.Float(string='ใบหุ้น จำนวนหุ้น (pt)', default=10.0)
    certificate_share_number_from_font_size_pt = fields.Float(string='ใบหุ้น หุ้นเริ่มต้น (pt)', default=10.0)
    certificate_share_number_to_font_size_pt = fields.Float(string='ใบหุ้น หุ้นสุดท้าย (pt)', default=10.0)
    certificate_paid_per_share_font_size_pt = fields.Float(string='ใบหุ้น ชำระต่อหุ้น (pt)', default=10.0)
    certificate_total_paid_font_size_pt = fields.Float(string='ใบหุ้น รวมชำระแล้ว (pt)', default=10.0)
    certificate_issue_day_font_size_pt = fields.Float(string='ใบหุ้น วันออกใบหุ้น (pt)', default=10.0)
    certificate_issue_month_font_size_pt = fields.Float(string='ใบหุ้น เดือนออกใบหุ้น (pt)', default=10.0)
    certificate_issue_year_font_size_pt = fields.Float(string='ใบหุ้น ปีออกใบหุ้น (pt)', default=10.0)
    certificate_director_one_font_size_pt = fields.Float(string='ใบหุ้น กรรมการ 1 (pt)', default=10.0)
    certificate_director_two_font_size_pt = fields.Float(string='ใบหุ้น กรรมการ 2 (pt)', default=10.0)

    margin_warning = fields.Char(compute='_compute_margin_warning')

    @api.constrains('margin_top_mm', 'margin_bottom_mm', 'margin_left_mm', 'margin_right_mm')
    def _check_page_setup(self):
        for record in self:
            if min(record.margin_top_mm, record.margin_bottom_mm,
                   record.margin_left_mm, record.margin_right_mm) < 0:
                raise ValidationError(_('ระยะขอบกระดาษต้องไม่ติดลบ'))
            if (record.margin_left_mm + record.margin_right_mm >= 297 or
                    record.margin_top_mm + record.margin_bottom_mm >= 210):
                raise ValidationError(_('ระยะขอบรวมต้องน้อยกว่าขนาดกระดาษ'))

    @api.depends('margin_top_mm', 'margin_bottom_mm', 'margin_left_mm', 'margin_right_mm',
                 *POSITION_FIELDS, *FONT_SIZE_FIELDS)
    def _compute_margin_warning(self):
        for record in self:
            outside = []
            for position, width in POSITION_WIDTHS.items():
                x = getattr(record, position + '_x_mm')
                y = getattr(record, position + '_y_mm')
                size = getattr(record, position + '_font_size_pt')
                if (x < record.margin_left_mm or x + width > 297 - record.margin_right_mm or
                        y < record.margin_top_mm or y + size * 0.4 > 210 - record.margin_bottom_mm):
                    outside.append(record._fields[position + '_x_mm'].string.replace(' แนวนอน (mm)', ''))
            record.margin_warning = (
                _('ตำแหน่งฟิลด์อยู่นอกพื้นที่ขอบที่กำหนด: %s') % ', '.join(outside)
                if outside else False
            )

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

    @api.constrains('stub_width_mm', *POSITION_FIELDS, *FONT_SIZE_FIELDS)
    def _check_layout_bounds(self):
        for record in self:
            if not 70 <= record.stub_width_mm <= 120:
                raise ValidationError(_('ความกว้างต้นขั้วต้องอยู่ระหว่าง 70-120 mm'))
            if any(not 0 <= getattr(record, name) <= 297 for name in POSITION_FIELDS if name.endswith('_x_mm')):
                raise ValidationError(_('ตำแหน่งแนวนอนต้องอยู่ระหว่าง 0-297 mm'))
            if any(not 0 <= getattr(record, name) <= 210 for name in POSITION_FIELDS if name.endswith('_y_mm')):
                raise ValidationError(_('ตำแหน่งแนวตั้งต้องอยู่ระหว่าง 0-210 mm'))
            if any(not 6 <= getattr(record, name) <= 30 for name in FONT_SIZE_FIELDS):
                raise ValidationError(_('ขนาดตัวอักษรต้องอยู่ระหว่าง 6-30 pt'))
