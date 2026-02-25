# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class AccountChequeConfig(models.Model):
    _name = 'account.cheque.config'
    _description = 'Account Cheque Print Configuration'
    
    name = fields.Char(string='Configuration Name', required=True, default='Default')
    
    # Page Layout Settings
    page_width_mm = fields.Float(string='Page Width (mm)', default=177.8, help='Width of the cheque in mm')
    page_height_mm = fields.Float(string='Page Height (mm)', default=88.9, help='Height of the cheque in mm')
    
    # Cheque Date Positions
    date_top = fields.Integer(string='Date - Top (px)', default=45, help='ตำแหน่งวันที่จากด้านบน')
    date_left = fields.Integer(string='Date - Left (px)', default=550, help='ตำแหน่งวันที่จากด้านซ้าย')
    date_spacing = fields.Integer(string='Date - Digit Spacing (px)', default=24, help='ระยะห่างระหว่างตัวเลขวันที่')
    
    # Payee Positions
    payee_top = fields.Integer(string='Payee - Top (px)', default=115, help='ตำแหน่งชื่อผู้รับเงินจากด้านบน')
    payee_left = fields.Integer(string='Payee - Left (px)', default=120, help='ตำแหน่งชื่อผู้รับเงินจากด้านซ้าย')
    
    # Amount in Words Positions
    amount_words_top = fields.Integer(string='Amount in Words - Top (px)', default=155, help='ตำแหน่งจำนวนเงินตัวอักษรจากด้านบน')
    amount_words_left = fields.Integer(string='Amount in Words - Left (px)', default=100, help='ตำแหน่งจำนวนเงินตัวอักษรจากด้านซ้าย')
    amount_words_width = fields.Integer(string='Amount in Words - Width (px)', default=450, help='ความกว้างสูงสุดของจำนวนเงินตัวอักษร')
    
    # Amount in Digits Positions
    amount_digits_top = fields.Integer(string='Amount in Digits - Top (px)', default=155, help='ตำแหน่งจำนวนเงินตัวเลขจากด้านบน')
    amount_digits_left = fields.Integer(string='Amount in Digits - Left (px)', default=580, help='ตำแหน่งจำนวนเงินตัวเลขจากด้านซ้าย')
    
    # Crossing Settings
    show_crossing = fields.Boolean(string='Show Crossing', default=True, help='แสดงการขีดคร่อมเช็ค')
    crossing_text = fields.Char(string='Crossing Text', default='A/C PAYEE ONLY', help='ข้อความขีดคร่อม')
    crossing_top = fields.Integer(string='Crossing - Top (px)', default=30)
    crossing_left = fields.Integer(string='Crossing - Left (px)', default=50)
    
    # Global Settings
    font_size = fields.Integer(string='Font Size (px)', default=16)
    font_family = fields.Char(string='Font Family', default='Sarabun, sans-serif')
    
    # Background Image for configuration guidance
    background_image = fields.Binary(string='Cheque Template Image', help='รูปภาพต้นแบบเช็คสำหรับใช้กะระยะ')
    show_background = fields.Boolean(string='Show Background', default=True)
    background_opacity = fields.Float(string='Background Opacity', default=0.5)
    
    active = fields.Boolean(default=True)
    is_default = fields.Boolean(string='Default Configuration', default=False)

    @api.constrains('is_default')
    def _check_default_unique(self):
        for record in self:
            if record.is_default:
                other_defaults = self.search([
                    ('id', '!=', record.id),
                    ('is_default', '=', True)
                ])
                if other_defaults:
                    other_defaults.write({'is_default': False})

    @api.model
    def get_default_config(self):
        config = self.search([('is_default', '=', True)], limit=1)
        if not config:
            config = self.search([], limit=1)
        if not config:
            config = self.create({
                'name': 'Default Cheque Layout',
                'is_default': True,
            })
        return config
    
    def action_preview_cheque(self):
        """Preview cheque with current configuration"""
        self.ensure_one()
        Voucher = self.env['account.payment.voucher']
        voucher = Voucher.search([('payment_type', '=', 'check')], limit=1)
        if not voucher:
             voucher = Voucher.search([], limit=1)
        if not voucher:
            raise ValidationError(_('No payment vouchers found for preview.'))
        
        return self.env.ref('buz_accounting_addon.action_report_print_cheque').report_action(voucher)
