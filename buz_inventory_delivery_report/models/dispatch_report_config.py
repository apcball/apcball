# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class DispatchReportConfig(models.Model):
    _name = 'dispatch.report.config'
    _description = 'Dispatch Report Print Position Configuration'
    
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
    doc_number_top = fields.Integer(string='Document Number - Top (px)', default=130,
                                    help='เลขที่เอกสาร - ตำแหน่งจากด้านบน')
    doc_number_left = fields.Integer(string='Document Number - Left (px)', default=240,
                                     help='เลขที่เอกสาร - ตำแหน่งจากด้านซ้าย')
    
    doc_date_top = fields.Integer(string='Document Date - Top (px)', default=130,
                                  help='วันที่เอกสาร - ตำแหน่งจากด้านบน')
    doc_date_left = fields.Integer(string='Document Date - Left (px)', default=580,
                                   help='วันที่เอกสาร - ตำแหน่งจากด้านซ้าย')
    
    so_number_top = fields.Integer(string='SO Number - Top (px)', default=155,
                                   help='เลขที่ SO - ตำแหน่งจากด้านบน')
    so_number_left = fields.Integer(string='SO Number - Left (px)', default=240,
                                    help='เลขที่ SO - ตำแหน่งจากด้านซ้าย')
    
    # Customer Information Positions (ข้อมูลลูกค้า)
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
    
    # Shipping Information (ข้อมูลการจัดส่ง)
    shipping_method_top = fields.Integer(string='Shipping Method - Top (px)', default=193,
                                        help='วิธีการจัดส่ง - ตำแหน่งจากด้านบน')
    shipping_method_left = fields.Integer(string='Shipping Method - Left (px)', default=620,
                                         help='วิธีการจัดส่ง - ตำแหน่งจากด้านซ้าย')
    
    # Vehicle Information Positions (ข้อมูลยานพาหนะ)
    vehicle_type_top = fields.Integer(string='Vehicle Type - Top (px)', default=220,
                                     help='ประเภทยานพาหนะ - ตำแหน่งจากด้านบน')
    vehicle_type_left = fields.Integer(string='Vehicle Type - Left (px)', default=560,
                                      help='ประเภทยานพาหนะ - ตำแหน่งจากด้านซ้าย')
    
    vehicle_plate_top = fields.Integer(string='Vehicle Plate - Top (px)', default=225,
                                      help='ทะเบียนรถ - ตำแหน่งจากด้านบน')
    vehicle_plate_left = fields.Integer(string='Vehicle Plate - Left (px)', default=660,
                                       help='ทะเบียนรถ - ตำแหน่งจากด้านซ้าย')
    
    driver_name_top = fields.Integer(string='Driver Name - Top (px)', default=257,
                                    help='ชื่อคนขับรถ - ตำแหน่งจากด้านบน')
    driver_name_left = fields.Integer(string='Driver Name - Left (px)', default=50,
                                     help='ชื่อคนขับรถ - ตำแหน่งจากด้านซ้าย')
    
    dispatch_location_top = fields.Integer(string='Dispatch Location - Top (px)', default=275,
                                          help='สถานที่จัดส่ง - ตำแหน่งจากด้านบน')
    dispatch_location_left = fields.Integer(string='Dispatch Location - Left (px)', default=210,
                                           help='สถานที่จัดส่ง - ตำแหน่งจากด้านซ้าย')
    
    # Product Table Positions (ตารางรายการสินค้า)
    table_top = fields.Integer(string='Product Table - Top (px)', default=350,
                              help='ตารางสินค้า - ตำแหน่งจากด้านบน')
    table_left = fields.Integer(string='Product Table - Left (px)', default=35,
                               help='ตารางสินค้า - ตำแหน่งจากด้านซ้าย')
    table_width = fields.Integer(string='Product Table - Width (px)', default=720,
                                 help='ความกว้างของตารางสินค้า')
    
    # Table Header Height
    table_header_height = fields.Integer(string='Table Header Height (px)', default=30,
                                        help='ความสูงของหัวตาราง')
    
    # Line item positions (relative to table)
    line_height = fields.Integer(string='Line Height (px)', default=28, 
                                help='ความสูงของแต่ละแถวสินค้า')
    max_lines_per_page = fields.Integer(string='Max Lines Per Page', default=15,
                                       help='จำนวนแถวสูงสุดต่อหน้า')
    
    # Column positions (relative to table left) - ตำแหน่งคอลัมน์
    col_no_left = fields.Integer(string='No. Column - Left Offset (px)', default=10,
                                 help='คอลัมน์ลำดับที่')
    col_no_width = fields.Integer(string='No. Column - Width (px)', default=40,
                                  help='ความกว้างคอลัมน์ลำดับที่')
    
    col_code_left = fields.Integer(string='Code Column - Left Offset (px)', default=55,
                                   help='คอลัมน์รหัสสินค้า')
    col_code_width = fields.Integer(string='Code Column - Width (px)', default=100,
                                    help='ความกว้างคอลัมน์รหัสสินค้า')
    
    col_name_left = fields.Integer(string='Name Column - Left Offset (px)', default=160,
                                   help='คอลัมน์ชื่อสินค้า')
    col_name_width = fields.Integer(string='Name Column - Width (px)', default=280,
                                    help='ความกว้างคอลัมน์ชื่อสินค้า')
    
    col_description_left = fields.Integer(string='Description Column - Left Offset (px)', default=285,
                                         help='คอลัมน์รายละเอียด')
    col_description_width = fields.Integer(string='Description Column - Width (px)', default=150,
                                          help='ความกว้างคอลัมน์รายละเอียด')
    
    col_qty_left = fields.Integer(string='Qty Column - Left Offset (px)', default=445,
                                  help='คอลัมน์จำนวน')
    col_qty_width = fields.Integer(string='Qty Column - Width (px)', default=70,
                                   help='ความกว้างคอลัมน์จำนวน')
    
    col_unit_left = fields.Integer(string='Unit Column - Left Offset (px)', default=520,
                                   help='คอลัมน์หน่วย')
    col_unit_width = fields.Integer(string='Unit Column - Width (px)', default=80,
                                    help='ความกว้างคอลัมน์หน่วย')
    
    col_unit_price_left = fields.Integer(string='Unit Price Column - Left Offset (px)', default=605,
                                        help='คอลัมน์ราคาต่อหน่วย')
    col_unit_price_width = fields.Integer(string='Unit Price Column - Width (px)', default=85,
                                         help='ความกว้างคอลัมน์ราคาต่อหน่วย')
    
    col_remark_left = fields.Integer(string='Remark Column - Left Offset (px)', default=595,
                                    help='คอลัมน์หมายเหตุ')
    col_remark_width = fields.Integer(string='Remark Column - Width (px)', default=120,
                                     help='ความกว้างคอลัมน์หมายเหตุ')
    
    # Footer Positions (ส่วนท้ายเอกสาร)
    total_qty_top = fields.Integer(string='Total Quantity - Top (px)', default=900,
                                  help='ยอดรวมจำนวน - ตำแหน่งจากด้านบน')
    total_qty_left = fields.Integer(string='Total Quantity - Left (px)', default=445,
                                   help='ยอดรวมจำนวน - ตำแหน่งจากด้านซ้าย')
    
    total_amount_top = fields.Integer(string='Total Amount - Top (px)', default=900,
                                     help='ยอดรวมเงิน - ตำแหน่งจากด้านบน')
    total_amount_left = fields.Integer(string='Total Amount - Left (px)', default=605,
                                      help='ยอดรวมเงิน - ตำแหน่งจากด้านซ้าย')
    
    note_top = fields.Integer(string='Note Section - Top (px)', default=920,
                             help='หมายเหตุ - ตำแหน่งจากด้านบน')
    note_left = fields.Integer(string='Note Section - Left (px)', default=40,
                              help='หมายเหตุ - ตำแหน่งจากด้านซ้าย')
    note_width = fields.Integer(string='Note Section - Width (px)', default=720,
                               help='ความกว้างของหมายเหตุ')
    
    # Signature Positions (ตำแหน่งลายเซ็น)
    signature_section_top = fields.Integer(string='Signature Section - Top (px)', default=980,
                                          help='ส่วนลายเซ็น - ตำแหน่งจากด้านบน')
    
    signature_sender_top = fields.Integer(string='Sender Signature - Top (px)', default=1000,
                                         help='ลายเซ็นผู้ส่ง - ตำแหน่งจากด้านบน')
    signature_sender_left = fields.Integer(string='Sender Signature - Left (px)', default=110,
                                          help='ลายเซ็นผู้ส่ง - ตำแหน่งจากด้านซ้าย')
    
    signature_checker_top = fields.Integer(string='Checker Signature - Top (px)', default=1000,
                                          help='ลายเซ็นผู้ตรวจสอบ - ตำแหน่งจากด้านบน')
    signature_checker_left = fields.Integer(string='Checker Signature - Left (px)', default=280,
                                           help='ลายเซ็นผู้ตรวจสอบ - ตำแหน่งจากด้านซ้าย')
    
    signature_receiver_top = fields.Integer(string='Receiver Signature - Top (px)', default=1000,
                                           help='ลายเซ็นผู้รับ - ตำแหน่งจากด้านบน')
    signature_receiver_left = fields.Integer(string='Receiver Signature - Left (px)', default=450,
                                            help='ลายเซ็นผู้รับ - ตำแหน่งจากด้านซ้าย')
    
    signature_approver_top = fields.Integer(string='Approver Signature - Top (px)', default=1000,
                                           help='ลายเซ็นผู้อนุมัติ - ตำแหน่งจากด้านบน')
    signature_approver_left = fields.Integer(string='Approver Signature - Left (px)', default=620,
                                            help='ลายเซ็นผู้อนุมัติ - ตำแหน่งจากด้านซ้าย')
    
    signature_line_height = fields.Integer(string='Signature Line Height (px)', default=50,
                                          help='ระยะห่างสำหรับลายเซ็น')
    signature_date_offset = fields.Integer(string='Signature Date Offset (px)', default=25,
                                          help='ระยะห่างวันที่ใต้ลายเซ็น')
    
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
    ], string='Paper Size', default='a4', required=True,
    help='ขนาดกระดาษ - A4 เหมาะสำหรับการพิมพ์ทั่วไป')
    
    page_width = fields.Integer(string='Page Width (px)', default=794, 
                               help='ความกว้างหน้า - A4 = 794px at 96 DPI (210mm) - Full Page Coverage')
    page_height = fields.Integer(string='Page Height (px)', default=1123,
                                help='ความสูงหน้า - A4 = 1123px at 96 DPI (297mm) - Full Page Coverage')
    
    page_width_mm = fields.Float(string='Page Width (mm)', default=210.0,
                                 help='ความกว้างหน้ากระดาษ (มิลลิเมตร)')
    page_height_mm = fields.Float(string='Page Height (mm)', default=297.0,
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
    show_borders = fields.Boolean(string='Show Table Borders', default=True,
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
    show_signatures = fields.Boolean(string='Show Signature Section', default=True,
                                    help='แสดงส่วนลายเซ็น')
    show_company_logo = fields.Boolean(string='Show Company Logo', default=True,
                                      help='แสดงโลโก้บริษัท')
    
    # Logo Position
    logo_top = fields.Integer(string='Logo - Top (px)', default=30,
                             help='โลโก้ - ตำแหน่งจากด้านบน')
    logo_left = fields.Integer(string='Logo - Left (px)', default=40,
                              help='โลโก้ - ตำแหน่งจากด้านซ้าย')
    logo_width = fields.Integer(string='Logo Width (px)', default=150,
                                help='ความกว้างโลโก้')
    logo_height = fields.Integer(string='Logo Height (px)', default=80,
                                 help='ความสูงโลโก้')
    
    # Company Info Position
    company_name_top = fields.Integer(string='Company Name - Top (px)', default=45,
                                     help='ชื่อบริษัท - ตำแหน่งจากด้านบน')
    company_name_left = fields.Integer(string='Company Name - Left (px)', default=200,
                                      help='ชื่อบริษัท - ตำแหน่งจากด้านซ้าย')
    
    company_address_top = fields.Integer(string='Company Address - Top (px)', default=65,
                                        help='ที่อยู่บริษัท - ตำแหน่งจากด้านบน')
    company_address_left = fields.Integer(string='Company Address - Left (px)', default=200,
                                         help='ที่อยู่บริษัท - ตำแหน่งจากด้านซ้าย')
    
    company_phone_top = fields.Integer(string='Company Phone - Top (px)', default=85,
                                      help='เบอร์โทรบริษัท - ตำแหน่งจากด้านบน')
    company_phone_left = fields.Integer(string='Company Phone - Left (px)', default=200,
                                       help='เบอร์โทรบริษัท - ตำแหน่งจากด้านซ้าย')
    
    # Document Title
    doc_title = fields.Char(string='Document Title', default='ใบจัดส่งสินค้า / DISPATCH',
                           help='ชื่อเอกสาร')
    doc_title_top = fields.Integer(string='Document Title - Top (px)', default=160,
                                   help='ชื่อเอกสาร - ตำแหน่งจากด้านบน')
    doc_title_left = fields.Integer(string='Document Title - Left (px)', default=300,
                                    help='ชื่อเอกสาร - ตำแหน่งจากด้านซ้าย')
    doc_title_size = fields.Integer(string='Document Title Font Size (px)', default=20,
                                    help='ขนาดตัวอักษรชื่อเอกสาร')
    
    @api.onchange('paper_size')
    def _onchange_paper_size(self):
        """Auto-fill page dimensions based on paper size at 96 DPI"""
        if self.paper_size == 'letter':
            self.page_width = 816  # 8.5 inches * 96 DPI
            self.page_height = 1056  # 11 inches * 96 DPI
            self.page_width_mm = 215.9
            self.page_height_mm = 279.4
        elif self.paper_size == 'a4':
            self.page_width = 794  # 210mm = 8.27 inches * 96 DPI
            self.page_height = 1123  # 297mm = 11.69 inches * 96 DPI
            self.page_width_mm = 210.0
            self.page_height_mm = 297.0
        elif self.paper_size == 'legal':
            self.page_width = 816  # 8.5 inches * 96 DPI
            self.page_height = 1344  # 14 inches * 96 DPI
            self.page_width_mm = 215.9
            self.page_height_mm = 355.6
        elif self.paper_size == 'a5':
            self.page_width = 559  # 148mm = 5.83 inches * 96 DPI
            self.page_height = 794  # 210mm = 8.27 inches * 96 DPI
            self.page_width_mm = 148.0
            self.page_height_mm = 210.0
        # For 'custom', do nothing - let user set manually
    
    @api.onchange('dpi')
    def _onchange_dpi(self):
        """Recalculate page dimensions when DPI changes"""
        if self.paper_size == 'a4':
            # A4 = 210mm x 297mm
            inches_width = 210.0 / 25.4  # Convert mm to inches
            inches_height = 297.0 / 25.4
            self.page_width = int(inches_width * self.dpi)
            self.page_height = int(inches_height * self.dpi)
    
    @api.onchange('print_mode')
    def _onchange_print_mode(self):
        """Auto-set DPI based on print mode"""
        mode_dpi_map = {
            'screen': 96,
            'draft': 150,
            'standard': 200,
            'high': 300,
        }
        if self.print_mode in mode_dpi_map:
            self.dpi = mode_dpi_map[self.print_mode]
    
    def get_mm_to_px(self, mm_value):
        """Convert millimeters to pixels based on current DPI"""
        inches = mm_value / 25.4
        return int(inches * self.dpi)
    
    def get_px_to_mm(self, px_value):
        """Convert pixels to millimeters based on current DPI"""
        inches = px_value / self.dpi
        return round(inches * 25.4, 2)
    
    @api.model
    def get_default_config(self):
        """Get the default configuration"""
        config = self.search([('is_default', '=', True)], limit=1)
        if not config:
            config = self.search([], limit=1)
        if not config:
            config = self.create({
                'name': 'Default A4 Full Coverage',
                'is_default': True,
                'margin_top': 0,
                'margin_bottom': 0,
                'margin_left': 0,
                'margin_right': 0,
            })
        return config
    
    def action_reset_to_a4_defaults(self):
        """Reset all positions to default A4 full coverage values"""
        self.ensure_one()
        self.write({
            'paper_size': 'a4',
            'margin_top': 0,
            'margin_bottom': 0,
            'margin_left': 0,
            'margin_right': 0,
            'page_width': 794,
            'page_height': 1123,
            'page_width_mm': 210.0,
            'page_height_mm': 297.0,
            'dpi': 96,
        })
        return True
    
    def action_apply_full_page_layout(self):
        """Apply layout optimized for full A4 page coverage"""
        self.ensure_one()
        # Set all margins to 0 for full coverage
        self.write({
            'margin_top': 0,
            'margin_bottom': 0,
            'margin_left': 0,
            'margin_right': 0,
            # Optimize table to use full width
            'table_left': 20,
            'table_width': 754,  # Full width minus minimal margins
            # Maximize vertical space
            'table_top': 280,
            'max_lines_per_page': 18,  # More lines per page
            'line_height': 26,  # Slightly reduced for more content
        })
        return True
    
    def write(self, vals):
        """Ensure only one default configuration"""
        if vals.get('is_default'):
            self.search([('id', '!=', self.id)]).write({'is_default': False})
        return super(DispatchReportConfig, self).write(vals)
    
    @api.model
    def create(self, vals):
        """Ensure only one default configuration"""
        if vals.get('is_default'):
            self.search([]).write({'is_default': False})
        return super(DispatchReportConfig, self).create(vals)
    
    @api.constrains('doc_number_top', 'doc_number_left', 'doc_date_top', 'doc_date_left',
                    'customer_name_top', 'customer_name_left', 'customer_address_top', 'customer_address_left',
                    'customer_address_line2_top', 'customer_address_line2_left',
                    'customer_phone_top', 'customer_phone_left', 'vehicle_type_top', 'vehicle_type_left',
                    'vehicle_plate_top', 'vehicle_plate_left', 'driver_name_top', 'driver_name_left',
                    'dispatch_location_top', 'dispatch_location_left', 'table_top', 'table_left',
                    'total_qty_top', 'total_qty_left', 'signature_sender_top', 'signature_sender_left',
                    'signature_receiver_top', 'signature_receiver_left', 'signature_checker_top', 'signature_checker_left',
                    'signature_approver_top', 'signature_approver_left', 'logo_top', 'logo_left',
                    'company_name_top', 'company_name_left', 'doc_title_top', 'doc_title_left',
                    'col_no_left', 'col_code_left', 'col_name_left', 'col_qty_left', 'col_unit_left', 'col_remark_left')
    def _check_position_within_page(self):
        """Validate that all positions are not negative (removed page bounds check)"""
        for record in self:
            # Check all 'top' fields - only check for negative values
            top_fields = {
                'doc_number_top': 'Document Number Top',
                'doc_date_top': 'Document Date Top',
                'customer_name_top': 'Customer Name Top',
                'customer_address_top': 'Customer Address Top',
                'customer_address_line2_top': 'Customer Address Line 2 Top',
                'customer_phone_top': 'Customer Phone Top',
                'vehicle_type_top': 'Vehicle Type Top',
                'vehicle_plate_top': 'Vehicle Plate Top',
                'driver_name_top': 'Driver Name Top',
                'dispatch_location_top': 'Dispatch Location Top',
                'table_top': 'Table Top',
                'total_qty_top': 'Total Quantity Top',
                'signature_sender_top': 'Sender Signature Top',
                'signature_receiver_top': 'Receiver Signature Top',
                'signature_checker_top': 'Checker Signature Top',
                'signature_approver_top': 'Approver Signature Top',
                'logo_top': 'Logo Top',
                'company_name_top': 'Company Name Top',
                'doc_title_top': 'Document Title Top',
            }
            
            for field_name, label in top_fields.items():
                value = getattr(record, field_name, 0)
                if value < 0:
                    raise ValidationError(_(
                        f'{label} ต้องไม่ติดลบ\n'
                        f'{label} must not be negative\n'
                        f'ค่าปัจจุบัน: {value}px'
                    ))
            
            # Check all 'left' fields - only check for negative values
            left_fields = {
                'doc_number_left': 'Document Number Left',
                'doc_date_left': 'Document Date Left',
                'customer_name_left': 'Customer Name Left',
                'customer_address_left': 'Customer Address Left',
                'customer_address_line2_left': 'Customer Address Line 2 Left',
                'customer_phone_left': 'Customer Phone Left',
                'vehicle_type_left': 'Vehicle Type Left',
                'vehicle_plate_left': 'Vehicle Plate Left',
                'driver_name_left': 'Driver Name Left',
                'dispatch_location_left': 'Dispatch Location Left',
                'table_left': 'Table Left',
                'total_qty_left': 'Total Quantity Left',
                'signature_sender_left': 'Sender Signature Left',
                'signature_receiver_left': 'Receiver Signature Left',
                'signature_checker_left': 'Checker Signature Left',
                'signature_approver_left': 'Approver Signature Left',
                'logo_left': 'Logo Left',
                'company_name_left': 'Company Name Left',
                'doc_title_left': 'Document Title Left',
                'col_no_left': 'Column No Left',
                'col_code_left': 'Column Code Left',
                'col_name_left': 'Column Name Left',
                'col_qty_left': 'Column Qty Left',
                'col_unit_left': 'Column Unit Left',
                'col_remark_left': 'Column Remark Left',
            }
            
            for field_name, label in left_fields.items():
                value = getattr(record, field_name, 0)
                if value < 0:
                    raise ValidationError(_(
                        f'{label} ต้องไม่ติดลบ\n'
                        f'{label} must not be negative\n'
                        f'ค่าปัจจุบัน: {value}px'
                    ))
    
    @api.constrains('page_width', 'page_height')
    def _check_page_dimensions(self):
        """Validate page dimensions are reasonable"""
        for record in self:
            if record.page_width < 100 or record.page_width > 5000:
                raise ValidationError(_(
                    'ความกว้างหน้ากระดาษไม่ถูกต้อง!\n'
                    'Page width is invalid!\n'
                    'ต้องอยู่ระหว่าง 100-5000px\n'
                    f'ค่าปัจจุบัน: {record.page_width}px'
                ))
            if record.page_height < 100 or record.page_height > 5000:
                raise ValidationError(_(
                    'ความสูงหน้ากระดาษไม่ถูกต้อง!\n'
                    'Page height is invalid!\n'
                    'ต้องอยู่ระหว่าง 100-5000px\n'
                    f'ค่าปัจจุบัน: {record.page_height}px'
                ))
    
    @api.constrains('font_size', 'font_size_header', 'font_size_small')
    def _check_font_sizes(self):
        """Validate font sizes are within reasonable range"""
        for record in self:
            if record.font_size and (record.font_size < 6 or record.font_size > 72):
                raise ValidationError(_(
                    'ขนาดตัวอักษรพื้นฐานไม่ถูกต้อง!\n'
                    'Base font size is invalid!\n'
                    'ต้องอยู่ระหว่าง 6-72px\n'
                    f'ค่าปัจจุบัน: {record.font_size}px'
                ))
            if record.font_size_header and (record.font_size_header < 6 or record.font_size_header > 72):
                raise ValidationError(_(
                    'ขนาดตัวอักษรหัวข้อไม่ถูกต้อง!\n'
                    'Header font size is invalid!\n'
                    'ต้องอยู่ระหว่าง 6-72px\n'
                    f'ค่าปัจจุบัน: {record.font_size_header}px'
                ))
            if record.font_size_small and (record.font_size_small < 6 or record.font_size_small > 72):
                raise ValidationError(_(
                    'ขนาดตัวอักษรเล็กไม่ถูกต้อง!\n'
                    'Small font size is invalid!\n'
                    'ต้องอยู่ระหว่าง 6-72px\n'
                    f'ค่าปัจจุบัน: {record.font_size_small}px'
                ))

    def action_preview_layout(self):
        """Open preview report for this configuration"""
        self.ensure_one()
        return self.env.ref('buz_inventory_delivery_report.action_dispatch_report_preview').report_action(self)
