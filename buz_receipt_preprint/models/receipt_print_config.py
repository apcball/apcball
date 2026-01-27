# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ReceiptPrintConfig(models.Model):
    _name = 'receipt.print.config'
    _description = 'Receipt Print Position Configuration'
    
    name = fields.Char(string='Configuration Name', required=True, default='Default')
    
    # Page Layout Settings - Letter Size for Receipt
    margin_top = fields.Float(string='Top Margin (mm)', default=3, 
                             help='Top margin for receipt page')
    margin_bottom = fields.Float(string='Bottom Margin (mm)', default=3,
                                help='Bottom margin for receipt page')
    margin_left = fields.Float(string='Left Margin (mm)', default=3,
                              help='Left margin for receipt page')
    margin_right = fields.Float(string='Right Margin (mm)', default=3,
                               help='Right margin for receipt page')
    
    # Receipt Header Section Positions (พิกัดหัวใบเสร็จ)
    receipt_number_top = fields.Integer(string='Receipt Number - Top (px)', default=207,
                                    help='เลขที่ใบเสร็จ - ตำแหน่งจากด้านบน')
    receipt_number_left = fields.Integer(string='Receipt Number - Left (px)', default=470,
                                     help='เลขที่ใบเสร็จ - ตำแหน่งจากด้านซ้าย')
    
    receipt_date_top = fields.Integer(string='Receipt Date - Top (px)', default=244,
                                  help='วันที่ใบเสร็จ - ตำแหน่งจากด้านบน')
    receipt_date_left = fields.Integer(string='Receipt Date - Left (px)', default=470,
                                   help='วันที่ใบเสร็จ - ตำแหน่งจากด้านซ้าย')
    
    # Customer/Payer Information Positions (ข้อมูลผู้จ่าย)
    payer_name_top = fields.Integer(string='Payer Name - Top (px)', default=300,
                                      help='ชื่อผู้จ่ายเงิน - ตำแหน่งจากด้านบน')
    payer_name_left = fields.Integer(string='Payer Name - Left (px)', default=95,
                                       help='ชื่อผู้จ่ายเงิน - ตำแหน่งจากด้านซ้าย')
    payer_name_width = fields.Integer(string='Payer Name - Max Width (px)', default=370,
                                           help='ความกว้างสูงสุดของชื่อผู้จ่าย')
    
    payer_address_top = fields.Integer(string='Payer Address - Top (px)', default=337,
                                         help='ที่อยู่ผู้จ่าย - ตำแหน่งจากด้านบน')
    payer_address_left = fields.Integer(string='Payer Address - Left (px)', default=95,
                                          help='ที่อยู่ผู้จ่าย - ตำแหน่งจากด้านซ้าย')
    payer_address_width = fields.Integer(string='Payer Address - Max Width (px)', default=560,
                                           help='ความกว้างสูงสุดของที่อยู่ผู้จ่าย')
    
    # Payment Description (รายละเอียดการชำระเงิน)
    payment_description_top = fields.Integer(string='Payment Description - Top (px)', default=413,
                                       help='รายละเอียด/คำอธิบาย - ตำแหน่งจากด้านบน')
    payment_description_left = fields.Integer(string='Payment Description - Left (px)', default=95,
                                        help='รายละเอียด - ตำแหน่งจากด้านซ้าย')
    payment_description_width = fields.Integer(string='Payment Description - Max Width (px)', default=560,
                                           help='ความกว้างสูงสุดของรายละเอียด')
    
    # Amount Section (จำนวนเงิน)
    amount_numbers_top = fields.Integer(string='Amount (Numbers) - Top (px)', default=490,
                                     help='จำนวนเงิน (ตัวเลข) - ตำแหน่งจากด้านบน')
    amount_numbers_left = fields.Integer(string='Amount (Numbers) - Left (px)', default=464,
                                      help='จำนวนเงิน (ตัวเลข) - ตำแหน่งจากด้านซ้าย')
    
    amount_words_top = fields.Integer(string='Amount (Words) - Top (px)', default=490,
                                     help='จำนวนเงิน (ตัวอักษร) - ตำแหน่งจากด้านบน')
    amount_words_left = fields.Integer(string='Amount (Words) - Left (px)', default=95,
                                      help='จำนวนเงิน (ตัวอักษร) - ตำแหน่งจากด้านซ้าย')
    amount_words_width = fields.Integer(string='Amount (Words) - Max Width (px)', default=340,
                                       help='ความกว้างสูงสุดของจำนวนเงินตัวอักษร')
    
    # Payment Method (วิธีการชำระเงิน)
    payment_method_top = fields.Integer(string='Payment Method - Top (px)', default=526,
                                        help='วิธีการชำระ - ตำแหน่งจากด้านบน')
    payment_method_left = fields.Integer(string='Payment Method - Left (px)', default=95,
                                         help='วิธีการชำระ - ตำแหน่งจากด้านซ้าย')
    
    # Order Lines / Items Table (รายการสินค้า/บริการ)
    show_order_lines = fields.Boolean(string='Show Order Lines', default=True,
                                      help='แสดงรายการสินค้า/บริการ')
    order_lines_top = fields.Integer(string='Order Lines - Top (px)', default=430,
                                     help='รายการสินค้า - ตำแหน่งจากด้านบน')
    order_lines_left = fields.Integer(string='Order Lines - Left (px)', default=95,
                                      help='รายการสินค้า - ตำแหน่งจากด้านซ้าย')
    order_lines_width = fields.Integer(string='Order Lines - Max Width (px)', default=620,
                                       help='ความกว้างตารางรายการสินค้า')
    order_lines_font_size = fields.Integer(string='Order Lines Font Size (px)', default=14,
                                          help='ขนาดตัวอักษรรายการสินค้า')
    order_lines_max_lines = fields.Integer(string='Max Lines to Display', default=10,
                                          help='จำนวนรายการสูงสุดที่แสดง (0 = แสดงทั้งหมด)')
    order_lines_line_height = fields.Integer(string='Order Line Height (px)', default=20,
                                            help='ความสูงของแต่ละรายการ')
    
    # Check/Transfer Details (รายละเอียดเช็ค/โอนเงิน)
    check_number_top = fields.Integer(string='Check Number - Top (px)', default=563,
                                      help='เลขที่เช็ค - ตำแหน่งจากด้านบน')
    check_number_left = fields.Integer(string='Check Number - Left (px)', default=148,
                                       help='เลขที่เช็ค - ตำแหน่งจากด้านซ้าย')
    
    bank_name_top = fields.Integer(string='Bank Name - Top (px)', default=563,
                                    help='ธนาคาร - ตำแหน่งจากด้านบน')
    bank_name_left = fields.Integer(string='Bank Name - Left (px)', default=345,
                                     help='ธนาคาร - ตำแหน่งจากด้านซ้าย')
    
    check_date_top = fields.Integer(string='Check Date - Top (px)', default=563,
                                    help='ลงวันที่เช็ค - ตำแหน่งจากด้านบน')
    check_date_left = fields.Integer(string='Check Date - Left (px)', default=541,
                                     help='ลงวันที่เช็ค - ตำแหน่งจากด้านซ้าย')
    
    # Signature Positions (ตำแหน่งลายเซ็น)
    signature_section_top = fields.Integer(string='Signature Section - Top (px)', default=800,
                                          help='ส่วนลายเซ็น - ตำแหน่งจากด้านบน')
    
    signature_payer_top = fields.Integer(string='Payer Signature - Top (px)', default=840,
                                         help='ลายเซ็นผู้จ่าย - ตำแหน่งจากด้านบน')
    signature_payer_left = fields.Integer(string='Payer Signature - Left (px)', default=95,
                                          help='ลายเซ็นผู้จ่าย - ตำแหน่งจากด้านซ้าย')
    
    signature_receiver_top = fields.Integer(string='Receiver Signature - Top (px)', default=840,
                                           help='ลายเซ็นผู้รับเงิน - ตำแหน่งจากด้านบน')
    signature_receiver_left = fields.Integer(string='Receiver Signature - Left (px)', default=464,
                                            help='ลายเซ็นผู้รับเงิน - ตำแหน่งจากด้านซ้าย')
    
    signature_line_height = fields.Integer(string='Signature Line Height (px)', default=60,
                                          help='ระยะห่างสำหรับลายเซ็น')
    signature_date_offset = fields.Integer(string='Signature Date Offset (px)', default=30,
                                          help='ระยะห่างวันที่ใต้ลายเซ็น')
    
    # Global Settings (การตั้งค่าทั่วไป)
    font_size = fields.Integer(
        string='Font Size (px)', 
        default=16,
        required=True,
        help='ขนาดตัวอักษรพื้นฐาน (Base font size for receipt text)'
    )
    font_size_header = fields.Integer(
        string='Header Font Size (px)', 
        default=18,
        required=True,
        help='ขนาดตัวอักษรหัวข้อ (Font size for headers)'
    )
    font_size_small = fields.Integer(
        string='Small Font Size (px)', 
        default=14,
        required=True,
        help='ขนาดตัวอักษรเล็ก (Font size for small text)'
    )
    font_family = fields.Char(
        string='Font Family', 
        default='THSarabunNew, TH Sarabun New, Arial',
        help='ชนิดตัวอักษร (Font family for receipt)'
    )
    
    line_spacing = fields.Float(string='Line Spacing', default=1.2,
                               help='ระยะห่างระหว่างบรรทัด')
    
    # Page Settings (การตั้งค่าหน้ากระดาษ) - Letter Size for Receipt
    paper_size = fields.Selection([
        ('letter', 'Letter (8.5" x 11")'),
        ('a4', 'A4 (210mm x 297mm)'),
        ('custom', 'Custom Size'),
    ], string='Paper Size', default='letter', required=True,
    help='ขนาดกระดาษ - Letter เหมาะสำหรับใบเสร็จ')
    
    page_width = fields.Integer(string='Page Width (px)', default=816, 
                               help='ความกว้างหน้า - Letter = 816px at 96 DPI (216mm)')
    page_height = fields.Integer(string='Page Height (px)', default=1056,
                                help='ความสูงหน้า - Letter = 1056px at 96 DPI (279mm)')
    
    page_width_mm = fields.Float(string='Page Width (mm)', default=216.0,
                                 help='ความกว้างหน้ากระดาษ (มิลลิเมตร)')
    page_height_mm = fields.Float(string='Page Height (mm)', default=279.0,
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
    background_image = fields.Binary(string='Background Image (Receipt Template)', 
                                     help='อัพโหลดรูปแบบใบเสร็จเพื่อช่วยในการตั้งค่าตำแหน่ง')
    background_image_filename = fields.Char(string='Filename')
    show_background = fields.Boolean(string='Show Background in Preview', default=True,
                                    help='แสดง/ซ่อนรูปพื้นหลังในหน้าตัวอย่าง')
    background_opacity = fields.Float(string='Background Opacity', default=0.3,
                                     help='ความโปร่งแสงของรูปพื้นหลัง (0.0 - 1.0)')
    
    # Border and Line Settings (เส้นขอบและเส้น)
    show_borders = fields.Boolean(string='Show Borders', default=False,
                                  help='แสดงเส้นขอบ')
    border_width = fields.Integer(string='Border Width (px)', default=1,
                                  help='ความหนาของเส้นขอบ')
    border_color = fields.Char(string='Border Color', default='#000000',
                              help='สีของเส้นขอบ (Hex color code)')
    
    # Header/Footer Toggle
    show_header = fields.Boolean(string='Show Header Section', default=True,
                                 help='แสดงส่วนหัวใบเสร็จ')
    show_footer = fields.Boolean(string='Show Footer Section', default=True,
                                 help='แสดงส่วนท้ายใบเสร็จ')
    show_signatures = fields.Boolean(string='Show Signature Section', default=True,
                                    help='แสดงส่วนลายเซ็น')
    
    # Additional Receipt-specific fields
    show_company_logo = fields.Boolean(string='Show Company Logo', default=True,
                                      help='แสดงโลโก้บริษัท')
    
    logo_top = fields.Integer(string='Logo - Top (px)', default=30,
                             help='โลโก้ - ตำแหน่งจากด้านบน')
    logo_left = fields.Integer(string='Logo - Left (px)', default=40,
                              help='โลโก้ - ตำแหน่งจากด้านซ้าย')
    logo_width = fields.Integer(string='Logo Width (px)', default=100,
                                help='ความกว้างโลโก้')
    
    # Tax Information Display
    show_tax_id = fields.Boolean(string='Show Tax ID', default=True,
                                help='แสดงเลขประจำตัวผู้เสียภาษี')
    tax_id_top = fields.Integer(string='Tax ID - Top (px)', default=600,
                                help='เลขผู้เสียภาษี - ตำแหน่งจากด้านบน')
    tax_id_left = fields.Integer(string='Tax ID - Left (px)', default=95,
                                 help='เลขผู้เสียภาษี - ตำแหน่งจากด้านซ้าย')
    
    # Validation Constraints
    @api.constrains('font_size', 'font_size_header', 'font_size_small')
    def _check_font_sizes(self):
        """Validate font sizes are within acceptable range"""
        for record in self:
            if record.font_size < 6 or record.font_size > 72:
                raise ValidationError(_('Base font size must be between 6 and 72 pixels.'))
            if record.font_size_header < 6 or record.font_size_header > 72:
                raise ValidationError(_('Header font size must be between 6 and 72 pixels.'))
            if record.font_size_small < 6 or record.font_size_small > 72:
                raise ValidationError(_('Small font size must be between 6 and 72 pixels.'))
    
    @api.constrains('background_opacity')
    def _check_opacity(self):
        """Validate opacity is between 0 and 1"""
        for record in self:
            if record.background_opacity < 0.0 or record.background_opacity > 1.0:
                raise ValidationError(_('Background opacity must be between 0.0 and 1.0'))
    
    @api.constrains('is_default')
    def _check_default_unique(self):
        """Ensure only one default configuration exists"""
        for record in self:
            if record.is_default:
                other_defaults = self.search([
                    ('is_default', '=', True),
                    ('id', '!=', record.id)
                ])
                if other_defaults:
                    other_defaults.write({'is_default': False})
    
    def action_reset_to_defaults(self):
        """Reset configuration to default values"""
        self.ensure_one()
        default_values = {
            'receipt_number_top': 207,
            'receipt_number_left': 470,
            'receipt_date_top': 244,
            'receipt_date_left': 470,
            'payer_name_top': 300,
            'payer_name_left': 95,
            'payer_address_top': 337,
            'payer_address_left': 95,
            'payment_description_top': 413,
            'payment_description_left': 95,
            'amount_numbers_top': 490,
            'amount_numbers_left': 464,
            'amount_words_top': 490,
            'amount_words_left': 95,
            'payment_method_top': 526,
            'payment_method_left': 95,
            'check_number_top': 563,
            'check_number_left': 148,
            'bank_name_top': 563,
            'bank_name_left': 345,
            'check_date_top': 563,
            'check_date_left': 541,
            'signature_payer_top': 840,
            'signature_payer_left': 95,
            'signature_receiver_top': 840,
            'signature_receiver_left': 464,
            'font_size': 16,
            'font_size_header': 18,
            'font_size_small': 14,
        }
        self.write(default_values)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Configuration reset to default values'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def toggle_active(self):
        """Toggle active state"""
        for record in self:
            record.active = not record.active
    
    @api.model
    def get_default_config(self):
        """Get the default configuration or create one if it doesn't exist"""
        config = self.search([('is_default', '=', True)], limit=1)
        if not config:
            config = self.search([], limit=1)
            if config:
                config.is_default = True
        return config
