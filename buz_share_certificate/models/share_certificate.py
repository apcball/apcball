from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


DATA_FIELDS = (
    'company_name', 'registration_number', 'certificate_number', 'issue_date',
    'shareholder_name', 'share_count', 'share_number_from', 'share_number_to',
    'registered_capital', 'total_shares', 'share_value', 'paid_per_share', 'total_paid',
    'previous_certificate_number', 'previous_certificate_date', 'receipt_date',
    'director_one', 'director_two',
)


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
