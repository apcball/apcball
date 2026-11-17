from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class ShareCertificateLayoutConfig(models.Model):
    _name = 'buz.share.certificate.layout.config'
    _description = 'Share Certificate Layout Configuration'
    _rec_name = 'name'

    name = fields.Char(required=True, default='ค่าเริ่มต้น')
    position_ids = fields.One2many(
        'buz.share.certificate.layout.position', 'config_id', string='ตำแหน่งค่าที่พิมพ์'
    )
    margin_top = fields.Float(
        compute='_compute_margins', inverse='_inverse_margin_top', digits=(6, 2), string='ขอบบน (mm)'
    )
    margin_bottom = fields.Float(
        compute='_compute_margins', inverse='_inverse_margin_bottom', digits=(6, 2), string='ขอบล่าง (mm)'
    )
    margin_left = fields.Float(
        compute='_compute_margins', inverse='_inverse_margin_left', digits=(6, 2), string='ขอบซ้าย (mm)'
    )
    margin_right = fields.Float(
        compute='_compute_margins', inverse='_inverse_margin_right', digits=(6, 2), string='ขอบขวา (mm)'
    )

    def _compute_margins(self):
        paperformat = self.env.ref('buz_share_certificate.paperformat_share_certificate')
        for config in self:
            config.margin_top = paperformat.margin_top
            config.margin_bottom = paperformat.margin_bottom
            config.margin_left = paperformat.margin_left
            config.margin_right = paperformat.margin_right

    def _inverse_margin_top(self):
        self.env.ref('buz_share_certificate.paperformat_share_certificate').margin_top = self.margin_top

    def _inverse_margin_bottom(self):
        self.env.ref('buz_share_certificate.paperformat_share_certificate').margin_bottom = self.margin_bottom

    def _inverse_margin_left(self):
        self.env.ref('buz_share_certificate.paperformat_share_certificate').margin_left = self.margin_left

    def _inverse_margin_right(self):
        self.env.ref('buz_share_certificate.paperformat_share_certificate').margin_right = self.margin_right

    def write(self, vals):
        margin_fields = {'margin_top', 'margin_bottom', 'margin_left', 'margin_right'}
        if margin_fields.intersection(vals):
            for config in self:
                margins = {field: vals.get(field, getattr(config, field)) for field in margin_fields}
                if any(value < 0 for value in margins.values()):
                    raise ValidationError('ระยะขอบกระดาษต้องไม่ติดลบ')
                if (
                    margins['margin_left'] + margins['margin_right'] >= 297
                    or margins['margin_top'] + margins['margin_bottom'] >= 210
                ):
                    raise ValidationError('ระยะขอบรวมต้องน้อยกว่าขนาดกระดาษ A4 แนวนอน')
        return super().write(vals)

    def get_position_style(self, code):
        self.ensure_one()
        position = next((item for item in self.position_ids if item.code == code), None)
        if not position:
            return 'display:none;'
        return 'left:%smm;top:%smm;font-size:%spt;' % (
            position.x_mm, position.y_mm, position.font_size_pt
        )

    @api.model
    def get_default_config(self):
        return self.search([], limit=1)

    def action_preview_layout(self):
        self.ensure_one()
        certificate_id = self.env.context.get('preview_certificate_id')
        certificate = self.env['buz.share.certificate.print.wizard'].browse(certificate_id).exists()
        if not certificate:
            raise UserError('กรุณาเปิดหน้าตั้งค่าจากใบหุ้นที่ต้องการดูตัวอย่าง')
        return self.env.ref('buz_share_certificate.action_report_share_certificate').report_action(
            certificate, config=False
        )


class ShareCertificateLayoutPosition(models.Model):
    _name = 'buz.share.certificate.layout.position'
    _description = 'Share Certificate Printed Value Position'
    _order = 'section, sequence, id'
    _rec_name = 'label'

    config_id = fields.Many2one(
        'buz.share.certificate.layout.config', required=True, ondelete='cascade'
    )
    code = fields.Char(required=True, readonly=True, index=True)
    label = fields.Char(required=True, readonly=True)
    section = fields.Selection(
        [('stub', 'ต้นขั้ว'), ('certificate', 'ใบหุ้น')], required=True, readonly=True
    )
    sequence = fields.Integer(default=10, readonly=True)
    x_mm = fields.Float(string='แนวนอน (mm)', digits=(6, 2))
    y_mm = fields.Float(string='แนวตั้ง (mm)', digits=(6, 2))
    font_size_pt = fields.Float(string='ขนาดฟอนต์ (pt)', digits=(4, 1), default=10, required=True)
    x_default_mm = fields.Float(digits=(6, 2), readonly=True)
    y_default_mm = fields.Float(digits=(6, 2), readonly=True)

    def action_reset_position(self):
        self.ensure_one()
        self.write({'x_mm': self.x_default_mm, 'y_mm': self.y_default_mm})

    @api.constrains('font_size_pt')
    def _check_font_size_pt(self):
        for position in self:
            if not 6 <= position.font_size_pt <= 72:
                raise ValidationError('ขนาดฟอนต์ต้องอยู่ระหว่าง 6 ถึง 72 pt')

    _sql_constraints = [
        ('config_code_unique', 'unique(config_id, code)', 'ตำแหน่งนี้มีอยู่แล้ว'),
    ]
