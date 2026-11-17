from odoo import fields, models


class ShareCertificate(models.Model):
    _name = 'buz.share.certificate.print.wizard'
    _description = 'Share Certificate'
    _rec_name = 'certificate_number'

    company_name = fields.Char(string='ชื่อบริษัท')
    company_registration_number = fields.Char(string='เลขทะเบียนบริษัท')
    certificate_number = fields.Char(string='เลขที่ใบหุ้น')
    issue_date = fields.Date(string='วันที่ออกใบหุ้น')
    shareholder_name = fields.Char(string='ชื่อผู้ถือหุ้น')
    registered_capital = fields.Float(string='ทุนจดทะเบียน', digits=(16, 2))
    registered_share_count = fields.Integer(string='จำนวนหุ้นจดทะเบียน')
    share_value = fields.Float(string='มูลค่าหุ้นละ', digits=(16, 2))
    share_count = fields.Integer(string='จำนวนหุ้นที่ถือ')
    share_number_from = fields.Char(string='หมายเลขหุ้นตั้งแต่')
    share_number_to = fields.Char(string='ถึง')
    paid_per_share = fields.Float(string='ชำระค่าหุ้นแล้ว หุ้นละ', digits=(16, 2))
    total_paid = fields.Float(string='รวมเป็นเงินค่าหุ้นที่ชำระแล้ว', digits=(16, 2))
    cancelled_certificate_number = fields.Char(string='เลขที่ใบหุ้นเดิมที่ยกเลิก')
    cancelled_date = fields.Date(string='วันที่ยกเลิกใบหุ้นเดิม')
    received_date = fields.Date(string='วันที่ผู้ถือหุ้นได้รับใบหุ้น')

    def action_open_layout_config(self):
        self.ensure_one()
        action = self.env.ref('buz_share_certificate.action_share_certificate_layout_config').read()[0]
        action['context'] = dict(self.env.context, preview_certificate_id=self.id)
        return action
