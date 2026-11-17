from odoo import api, fields, models


class ShareCertificateLayoutConfig(models.Model):
    _name = 'buz.share.certificate.layout.config'
    _description = 'Share Certificate Layout Configuration'
    _rec_name = 'name'

    name = fields.Char(required=True, default='ค่าเริ่มต้น')
    position_ids = fields.One2many(
        'buz.share.certificate.layout.position', 'config_id', string='ตำแหน่งค่าที่พิมพ์'
    )

    def get_position_style(self, code):
        self.ensure_one()
        position = next((item for item in self.position_ids if item.code == code), None)
        if not position:
            return 'display:none;'
        return 'left:%smm;top:%smm;' % (position.x_mm, position.y_mm)

    @api.model
    def get_default_config(self):
        return self.search([], limit=1)


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
    x_default_mm = fields.Float(digits=(6, 2), readonly=True)
    y_default_mm = fields.Float(digits=(6, 2), readonly=True)

    def action_reset_position(self):
        self.ensure_one()
        self.write({'x_mm': self.x_default_mm, 'y_mm': self.y_default_mm})

    _sql_constraints = [
        ('config_code_unique', 'unique(config_id, code)', 'ตำแหน่งนี้มีอยู่แล้ว'),
    ]
