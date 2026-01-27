# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AccountReceiptConfig(models.Model):
    _name = 'account.receipt.config'
    _description = 'Account Receipt Preprint Configuration'
    
    name = fields.Char(string='Configuration Name', required=True, default='Default')
    
    # Page Layout Settings - A4 optimized
    margin_top = fields.Float(string='Top Margin (mm)', default=0, 
                             help='Top margin for A4 page (0mm for full coverage)')
    margin_bottom = fields.Float(string='Bottom Margin (mm)', default=0,
                                help='Bottom margin for A4 page (0mm for full coverage)')
    margin_left = fields.Float(string='Left Margin (mm)', default=0,
                              help='Left margin for A4 page (0mm for full coverage)')
    margin_right = fields.Float(string='Right Margin (mm)', default=0,
                               help='Right margin for A4 page (0mm for full coverage)')
    
    # Header Section Positions (พิกัดหัวกระดาษ)
    receipt_number_top = fields.Integer(string='Receipt Number - Top (px)', default=130,
                                       help='เลขที่ใบเสร็จ - ตำแหน่งจากด้านบน')
    receipt_number_left = fields.Integer(string='Receipt Number - Left (px)', default=240,
                                        help='เลขที่ใบเสร็จ - ตำแหน่งจากด้านซ้าย')
    
    receipt_date_top = fields.Integer(string='Receipt Date - Top (px)', default=130,
                                     help='วันที่ใบเสร็จ - ตำแหน่งจากด้านบน')
    receipt_date_left = fields.Integer(string='Receipt Date - Left (px)', default=580,
                                      help='วันที่ใบเสร็จ - ตำแหน่งจากด้านซ้าย')
    
    # Customer Information Positions (ข้อมูลลูกค้า)
    customer_code_top = fields.Integer(string='Customer Code - Top (px)', default=193,
                                       help='รหัสลูกค้า - ตำแหน่งจากด้านบน')
    customer_code_left = fields.Integer(string='Customer Code - Left (px)', default=140,
                                        help='รหัสลูกค้า - ตำแหน่งจากด้านซ้าย')
    
    customer_name_top = fields.Integer(string='Customer Name - Top (px)', default=193,
                                      help='ชื่อลูกค้า - ตำแหน่งจากด้านบน')
    customer_name_left = fields.Integer(string='Customer Name - Left (px)', default=210,
                                       help='ชื่อลูกค้า - ตำแหน่งจากด้านซ้าย')
    
    customer_address_top = fields.Integer(string='Customer Address - Top (px)', default=225,
                                         help='ที่อยู่ลูกค้า - ตำแหน่งจากด้านบน')
    customer_address_left = fields.Integer(string='Customer Address - Left (px)', default=210,
                                          help='ที่อยู่ลูกค้า - ตำแหน่งจากด้านซ้าย')
    customer_address_width = fields.Integer(string='Customer Address - Max Width (px)', default=300,
                                           help='ความกว้างสูงสุดของที่อยู่')
    
    customer_address_line2_top = fields.Integer(string='Customer Address Line 2 - Top (px)', default=245,
                                               help='ที่อยู่ลูกค้าบรรทัด 2 (อำเภอ จังหวัด รหัสไปรษณีย์) - ตำแหน่งจากด้านบน')
    customer_address_line2_left = fields.Integer(string='Customer Address Line 2 - Left (px)', default=210,
                                                help='ที่อยู่ลูกค้าบรรทัด 2 - ตำแหน่งจากด้านซ้าย')
    
    customer_phone_top = fields.Integer(string='Customer Phone - Top (px)', default=257,
                                       help='เบอร์โทรศัพท์ - ตำแหน่งจากด้านบน')
    customer_phone_left = fields.Integer(string='Customer Phone - Left (px)', default=587,
                                        help='เบอร์โทรศัพท์ - ตำแหน่งจากด้านซ้าย')
    
    customer_taxid_top = fields.Integer(string='Customer Tax ID - Top (px)', default=275,
                                       help='เลขประจำตัวผู้เสียภาษี - ตำแหน่งจากด้านบน')
    customer_taxid_left = fields.Integer(string='Customer Tax ID - Left (px)', default=210,
                                        help='เลขประจำตัวผู้เสียภาษี - ตำแหน่งจากด้านซ้าย')
    
    # Invoice Lines Table Positions (ตารางรายการใบแจ้งหนี้)
    table_top = fields.Integer(string='Invoice Table - Top (px)', default=350,
                              help='ตารางใบแจ้งหนี้ - ตำแหน่งจากด้านบน')
    table_left = fields.Integer(string='Invoice Table - Left (px)', default=35,
                               help='ตารางใบแจ้งหนี้ - ตำแหน่งจากด้านซ้าย')
    table_width = fields.Integer(string='Invoice Table - Width (px)', default=720,
                                 help='ความกว้างของตารางใบแจ้งหนี้')
    
    # Table Header Height
    table_header_height = fields.Integer(string='Table Header Height (px)', default=30,
                                        help='ความสูงของหัวตาราง')
    
    # Line item positions (relative to table)
    line_height = fields.Integer(string='Line Height (px)', default=28, 
                                help='ความสูงของแต่ละแถว')
    max_lines_per_page = fields.Integer(string='Max Lines Per Page', default=15,
                                       help='จำนวนแถวสูงสุดต่อหน้า')
    
    # Column positions (relative to table left) - ตำแหน่งคอลัมน์
    col_no_left = fields.Integer(string='No. Column - Left Offset (px)', default=10,
                                 help='คอลัมน์ลำดับที่')
    col_no_width = fields.Integer(string='No. Column - Width (px)', default=40,
                                  help='ความกว้างคอลัมน์ลำดับที่')
    
    col_invoice_left = fields.Integer(string='Invoice Column - Left Offset (px)', default=55,
                                     help='คอลัมน์เลขที่ใบแจ้งหนี้')
    col_invoice_width = fields.Integer(string='Invoice Column - Width (px)', default=120,
                                      help='ความกว้างคอลัมน์เลขที่ใบแจ้งหนี้')
    
    col_date_left = fields.Integer(string='Date Column - Left Offset (px)', default=180,
                                   help='คอลัมน์วันที่')
    col_date_width = fields.Integer(string='Date Column - Width (px)', default=90,
                                    help='ความกว้างคอลัมน์วันที่')
    
    col_total_left = fields.Integer(string='Total Column - Left Offset (px)', default=275,
                                   help='คอลัมน์ยอดรวม')
    col_total_width = fields.Integer(string='Total Column - Width (px)', default=100,
                                    help='ความกว้างคอลัมน์ยอดรวม')
    
    # Footer/Summary Positions (ส่วนสรุปยอด)
    summary_top = fields.Integer(string='Summary Section - Top (px)', default=800,
                                help='ส่วนสรุปยอด - ตำแหน่งจากด้านบน')
    
    total_payment_top = fields.Integer(string='Total Payment - Top (px)', default=820,
                                      help='ยอดชำระรวม - ตำแหน่งจากด้านบน')
    total_payment_left = fields.Integer(string='Total Payment - Left (px)', default=275,
                                       help='ยอดชำระรวม - ตำแหน่งจากด้านซ้าย')
    
    amount_in_words_top = fields.Integer(string='Amount in Words - Top (px)', default=840,
                                        help='จำนวนเงินเป็นตัวอักษร - ตำแหน่งจากด้านบน')
    amount_in_words_left = fields.Integer(string='Amount in Words - Left (px)', default=35,
                                         help='จำนวนเงินเป็นตัวอักษร - ตำแหน่งจากด้านซ้าย')
    amount_in_words_width = fields.Integer(string='Amount in Words - Width (px)', default=720,
                                          help='ความกว้างของจำนวนเงินเป็นตัวอักษร')
    
    # Global Settings (การตั้งค่าทั่วไป)
    font_size = fields.Integer(
        string='Font Size (px)', 
        default=14,
        required=True,
        help='ขนาดตัวอักษรพื้นฐาน (Base font size for report text)'
    )
    font_size_header = fields.Integer(
        string='Header Font Size (px)', 
        default=16,
        required=True,
        help='ขนาดตัวอักษรหัวข้อ (Font size for headers)'
    )
    font_size_small = fields.Integer(
        string='Small Font Size (px)', 
        default=12,
        required=True,
        help='ขนาดตัวอักษรเล็ก (Font size for small text)'
    )
    font_family = fields.Char(
        string='Font Family', 
        default='Sarabun, TH Sarabun New, Arial',
        help='ชนิดตัวอักษร (Font family for report)'
    )
    
    line_spacing = fields.Float(string='Line Spacing', default=1.2,
                               help='ระยะห่างระหว่างบรรทัด')
    
    # Page Settings (การตั้งค่าหน้ากระดาษ)
    paper_size = fields.Selection([
        ('letter', 'Letter (8.5" x 11")'),
        ('a4', 'A4 (210mm x 297mm)'),
        ('legal', 'Legal (8.5" x 14")'),
        ('a5', 'A5 (148mm x 210mm)'),
        ('custom', 'Custom Size'),
    ], string='Paper Size', default='letter', required=True,
    help='ขนาดกระดาษ - Letter เหมาะสำหรับการพิมพ์ทั่วไป')
    
    page_width = fields.Integer(string='Page Width (px)', default=816, 
                               help='ความกว้างหน้า - Letter = 816px at 96 DPI (215.9mm) - Full Page Coverage')
    page_height = fields.Integer(string='Page Height (px)', default=1056,
                                help='ความสูงหน้า - Letter = 1056px at 96 DPI (279.4mm) - Full Page Coverage')
    
    page_width_mm = fields.Float(string='Page Width (mm)', default=215.9,
                                 help='ความกว้างหน้ากระดาษ (มิลลิเมตร)')
    page_height_mm = fields.Float(string='Page Height (mm)', default=279.4,
                                  help='ความสูงหน้ากระดาษ (มิลลิเมตร)')
    
    dpi = fields.Integer(string='DPI (Dots Per Inch)', default=96,
                        help='ความละเอียดการพิมพ์ (96 DPI = standard screen, 300 DPI = high quality print)')
    
    # Print Quality Settings
    print_mode = fields.Selection([
        ('screen', 'Screen Preview (96 DPI)'),
        ('draft', 'Draft Print (150 DPI)'),
        ('standard', 'Standard Print (200 DPI)'),
        ('high', 'High Quality (300 DPI)'),
    ], string='Print Quality', default='screen',
    help='คุณภาพการพิมพ์')
    
    # Content Alignment
    text_align = fields.Selection([
        ('left', 'Left'),
        ('center', 'Center'),
        ('right', 'Right'),
    ], string='Default Text Alignment', default='left',
    help='การจัดตำแหน่งข้อความพื้นฐาน')
    
    header_align = fields.Selection([
        ('left', 'Left'),
        ('center', 'Center'),
        ('right', 'Right'),
    ], string='Header Alignment', default='center',
    help='การจัดตำแหน่งหัวเอกสาร')
    
    active = fields.Boolean(string='Active', default=True)
    is_default = fields.Boolean(string='Default Configuration', default=False,
                               help='ตั้งค่านี้เป็นค่าเริ่มต้น')
    
    # Background Image (รูปพื้นหลังสำหรับตั้งค่าตำแหน่ง)
    background_image = fields.Binary(string='Background Image (Form Template)', 
                                     help='อัพโหลดรูปแบบฟอร์มเพื่อช่วยในการตั้งค่าตำแหน่ง')
    background_image_filename = fields.Char(string='Filename')
    show_background = fields.Boolean(string='Show Background in Preview', default=True,
                                    help='แสดง/ซ่อนรูปพื้นหลังในหน้าตัวอย่าง')
    background_opacity = fields.Float(string='Background Opacity', default=0.3,
                                     help='ความโปร่งแสงของรูปพื้นหลัง (0.0 - 1.0)')
    
    # Border and Line Settings (เส้นขอบและเส้นตาราง)
    show_borders = fields.Boolean(string='Show Table Borders', default=False,
                                  help='แสดงเส้นขอบตาราง')
    border_width = fields.Integer(string='Border Width (px)', default=1,
                                  help='ความหนาของเส้นขอบ')
    border_color = fields.Char(string='Border Color', default='#000000',
                              help='สีของเส้นขอบ (Hex color code)')
    
    # Header/Footer Toggle
    show_header = fields.Boolean(string='Show Header Section', default=True,
                                 help='แสดงส่วนหัวเอกสาร')
    show_footer = fields.Boolean(string='Show Footer Section', default=True,
                                 help='แสดงส่วนท้ายเอกสาร')
    
    @api.constrains('font_size', 'font_size_header', 'font_size_small')
    def _check_font_sizes(self):
        """Validate font size values"""
        for record in self:
            if record.font_size < 8 or record.font_size > 72:
                raise ValidationError(_('Font size must be between 8 and 72 pixels.'))
            if record.font_size_header < 8 or record.font_size_header > 72:
                raise ValidationError(_('Header font size must be between 8 and 72 pixels.'))
            if record.font_size_small < 8 or record.font_size_small > 72:
                raise ValidationError(_('Small font size must be between 8 and 72 pixels.'))
    
    @api.constrains('is_default')
    def _check_default_unique(self):
        """Ensure only one default configuration"""
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
        """Get the default configuration"""
        config = self.search([('is_default', '=', True)], limit=1)
        if not config:
            config = self.search([], limit=1)
        if not config:
            config = self.create({
                'name': 'Default Letter Receipt',
                'is_default': True,
                'margin_top': 0,
                'margin_bottom': 0,
                'margin_left': 0,
                'margin_right': 0,
            })
        return config
    
    def action_reset_to_letter_defaults(self):
        """Reset all positions to default Letter full coverage values"""
        self.ensure_one()
        self.write({
            'paper_size': 'letter',
            'margin_top': 0,
            'margin_bottom': 0,
            'margin_left': 0,
            'margin_right': 0,
            'page_width': 816,
            'page_height': 1056,
            'page_width_mm': 215.9,
            'page_height_mm': 279.4,
            'dpi': 96,
        })
        return True
    
    def action_preview_receipt(self):
        """Preview receipt with current configuration"""
        self.ensure_one()
        # Find a receipt to preview or use demo data
        Receipt = self.env['account.receipt']
        receipt = Receipt.search([], limit=1)
        if not receipt:
            raise ValidationError(_('No receipts found for preview. Please create a receipt first.'))
        
        return self.env.ref('buz_account_receipt.action_report_account_receipt_preprint').report_action(receipt)
    
    @api.model
    def px_to_mm(self, px, dpi=96):
        """Convert pixels to millimeters
        Default DPI: 96 (standard screen resolution)
        1 inch = 25.4mm
        """
        inches = px / dpi
        return round(inches * 25.4, 2)
    
    @api.model
    def mm_to_px(self, mm, dpi=96):
        """Convert millimeters to pixels"""
        inches = mm / 25.4
        return round(inches * dpi)
