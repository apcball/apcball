from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import requests
import json
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class EtaxTransaction(models.Model):
    _name = 'etax.transaction'
    _description = 'ธุรกรรม E-Tax'
    _order = 'create_date desc'
    _rec_name = 'document_id'

    # ข้อมูลพื้นฐาน
    document_id = fields.Char('เลขที่เอกสาร', required=False)
    document_type = fields.Selection([
        ('T03', 'ใบแจ้งหนี้/ใบกำกับภาษี'),
        ('81', 'ใบลดหนี้'),
        ('80', 'ใบเพิ่มหนี้'),
    ], 'ประเภทเอกสาร', default='T03', required=True)
    
    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('sending', 'กำลังส่ง'),
        ('sent', 'ส่งสำเร็จ'),
        ('error', 'ข้อผิดพลาด'),
    ], 'สถานะ', default='draft')
    
    journal_entry_memo = fields.Char(
        string='เลขที่อ้างอิง',
        compute='_compute_journal_entry_info',
        help='เลขที่อ้างอิงจาก invoice'
    )

    # ฟิลด์ Many2one สำหรับเลือก invoice (แสดงเป็น dropdown)
    selected_invoice_id = fields.Many2one(
        'account.move',
        string='เลขที่อ้างอิง (Invoice)',
        domain="[('id', 'in', invoice_ids)]"
    )
    
    # ฟิลด์เก็บรายการ invoice IDs ทั้งหมด (ใช้สำหรับ domain)
    invoice_ids = fields.Many2many(
        'account.move',
        string='Related Invoices',
        compute='_compute_invoice_ids'
    )

    selected_delivery_id = fields.Many2one(
        'stock.picking',
        string='เลขที่อ้างอิง (Delivery)',
        domain="[('id', 'in', delivery_ids)]",
        ondelete='set null'
    )
    
    # ฟิลด์เก็บรายการ Delivery Order IDs ทั้งหมด (ใช้สำหรับ domain)
    delivery_ids = fields.Many2many(
        'stock.picking',
        string='Related Delivery Orders',
        compute='_compute_delivery_ids'
    )

    # ข้อมูล API
    etax_config_id = fields.Many2one('etax.config', 'การตั้งค่า E-Tax', required=False)
    transaction_code = fields.Char('รหัสธุรกรรม E-Tax', readonly=True)
    
    # ข้อมูลลูกค้า
    partner_id = fields.Many2one('res.partner', 'ลูกค้า', required=True)
    partner_tax_id = fields.Char('เลขประจำตัวผู้เสียภาษีลูกค้า')
    partner_branch_id = fields.Char('รหัสสาขาลูกค้า', default='00000')
    
    # ข้อมูลเอกสาร
    invoice_id = fields.Many2one('account.move', 'ใบแจ้งหนี้อ้างอิง')

    sale_order_ref = fields.Many2one(
        'sale.order',
        string='ใบสั่งขายอ้างอิง',
        domain="[('partner_id', '=', partner_id), ('state', 'in', ['sale', 'done'])]"
    )
    
    # วันที่
    document_date = fields.Datetime('วันที่เอกสาร', default=fields.Datetime.now)
    payment_term = fields.Integer('เงื่อนไขการชำระเงิน')
    payment_due_date = fields.Date('วันครบกำหนดชำระ')
    
    # จำนวนเงิน
    original_amount = fields.Float('มูลค่าตามใบกำกับภาษีเดิม', compute='_compute_original_amount')
    amount_untaxed = fields.Float('มูลค่าที่ถูกต้อง', compute='_compute_amount_untaxed')
    net_amount = fields.Float(
        'มูลค่าสินค้าที่นำมาคิดภาษี',
        compute='_compute_net_amount'
    )

    difference_amount = fields.Float('ผลต่าง', compute='_compute_difference_amount')
    amount_tax = fields.Float('ภาษีมูลค่าเพิ่ม', compute='_compute_amount_tax')
    amount_vat = fields.Float('ภาษีมูลค่าเพิ่ม', compute='_compute_net_amount_tax')
    amount_total = fields.Float('รวมจำนวนเงิน', compute='_compute_amount_total')
    net_amount_total = fields.Float('รวมจำนวนเงิน', compute='_compute_net_amount_total')
    amount_disc = fields.Float('ส่วนลด', compute='_compute_amount_disc')
    invoice_total = fields.Float('ยอดรวมใบแจ้งหนี้', compute='_compute_invoice_total')
    deposit = fields.Float('หักมัดจำ', default=0.0)
    total_after_deposit = fields.Float('ยอดหลังหักมัดจำ', compute='_compute_total_after_deposit')

    currency_id = fields.Many2one('res.currency', 'สกุลเงิน', 
                                 default=lambda self: self.env.company.currency_id)
    
    # ผลลัพธ์จาก API
    pdf_url = fields.Char('URL ไฟล์ PDF', readonly=True)
    xml_url = fields.Char('URL ไฟล์ XML', readonly=True)
    api_response = fields.Text('ผลตอบกลับจาก API', readonly=True)
    error_message = fields.Text('ข้อความข้อผิดพลาด', readonly=True)
    
    # รายการสินค้า
    line_ids = fields.One2many('etax.transaction.line', 'transaction_id', 'รายการสินค้า')
    
    # หมายเหตุ
    remark_discount = fields.Text('เหตุผลในการลดหนี้')
    remark_cdn = fields.Selection([
        ('CDNG01', 'ลดราคาสินค้าที่ขาย (สินค้าผิดข้อกำหนดที่ตกลงกัน)'),
        ('CDNG02', 'สินค้าชำรุดเสียหาย'),
        ('CDNG03', 'สินค้าขาดจำนวนตามที่ตกลงซื้อขาย'),
        ('CDNG04', 'คำนวณราคาสินค้า ผิดพลาดสูงกว่าที่เป็นจริง'),
        ('CDNG05', 'รับคืนสินค้า (ไม่ตรงตามคำพรรณนา)'),
        ('CDNG99', 'เหตุอื่น (ระบุสาเหตุ)'),
        ('CDNS01', 'ลดราคาค่าบริการ (บริการผิดข้อกำหนดที่ตกลงกัน)'),
        ('CDNS02', 'ค่าบริการขาดจำนวน'),
        ('CDNS03', 'คำนวณราคาค่าบริการผิดพลาดสูงกว่าที่เป็นจริง'),
        ('CDNS04', 'บอกเลิกสัญญาบริการ'),
        ('CDNS99', 'เหตุอื่น (ระบุสาเหตุ)'),
    ], 'เหตุผลในการลดหนี้', default='', required=False)

    remark_dbn = fields.Selection([
        ('DBNG01', 'มีการเพิ่มราคาค่าสินค้า (สินค้าเกินกว่าจำนวนที่ตกลงกัน)'),
        ('DBNG02', 'คำนวณราคาสินค้า ผิดพลาดต่ำกว่าราคาที่เป็นจริง'),
        ('DBNG99', 'เหตุอื่น (ระบุสาเหตุ)'),
        ('DBNS01', 'การเพิ่มราคาค่าบริการ (บริการเกินกว่าข้อกำหนดที่ตกลงกัน)'),
        ('DBNS02', 'คำนวณราคาค่าบริการ ผิดพลาดต่ำกว่าราคาที่เป็นจริง'),
        ('DBNS99', 'เหตุอื่น (ระบุสาเหตุ)'),
    ], 'เหตุผลในการเพิ่มหนี้', default='', required=False)
    
    notes = fields.Text('หมายเหตุ')

    @api.onchange('partner_id')
    def _onchange_partner_id_sale_order(self):
        # รีเซ็ต sale_order_ref และ journal_entry_memo เมื่อเปลี่ยน customer
        self.sale_order_ref = False
        self.selected_invoice_id = False
        self.selected_delivery_id = False
        
        # ดึง Tax Branch จาก partner
        if self.partner_id:
            self.partner_tax_id = self.partner_id.vat or ''
            self.partner_branch_id = self.partner_id.branch or '00000'
        else:
            self.partner_branch_id = '00000'

        # สร้าง domain
        if self.partner_id:
            return {
                'domain': {
                    'sale_order_ref': [
                        ('partner_id', '=', self.partner_id.name),
                        ('state', 'in', ['sale', 'done'])
                    ]
                }
            }
        else:
            return {
                'domain': {
                    'sale_order_ref': [('id', '=', False)]  # ไม่แสดงอะไรเลยถ้าไม่เลือก customer
                }
            }

    @api.onchange('sale_order_ref')
    def _onchange_sale_order_ref(self):
        # รีเซ็ต selected_delivery_id เมื่อเปลี่ยน sale_order_ref
        self.selected_invoice_id = False
        self.selected_delivery_id = False
        
        # สร้าง domain สำหรับ selected_invoice_id
        # if self.sale_order_ref and self.sale_order_ref.name:
        #     sale_number = self.sale_order_ref.name
            # self.notes = sale_number

    @api.depends('sale_order_ref', 'partner_id')
    def _compute_invoice_ids(self):
        """คำนวณรายการ invoices ที่เกี่ยวข้อง"""
        for record in self:
            invoices = self.env['account.move']
            
            if record.sale_order_ref:
                # กรณีมี sale order reference
                invoices = record.sale_order_ref.invoice_ids.filtered(
                    lambda m: m.move_type in ('out_invoice', 'out_refund') 
                    and m.state == 'posted'
                    and m.id != record.invoice_id.id
                )
            elif record.partner_id:
                # กรณีมีแค่ customer แต่ไม่มี sale order
                invoices = self.env['account.move'].search([
                    ('partner_id', '=', record.partner_id.id),
                    ('move_type', 'in', ('out_invoice', 'out_refund')),
                    ('state', '=', 'posted'),
                    ('id', '!=', record.invoice_id.id)
                ])
            
            record.invoice_ids = invoices
            
    @api.depends('sale_order_ref', 'partner_id')
    def _compute_delivery_ids(self):
        """คำนวณรายการ Delivery Orders ที่เกี่ยวข้อง"""
        for record in self:
            pickings = self.env['stock.picking']
            
            if record.sale_order_ref:
                # กรณีมี sale order reference - ดึง Delivery Orders ทั้งหมดจาก sale order
                # ค้นหาจาก picking_ids ของ sale order (รวมทุก type: incoming, outgoing, internal)
                all_pickings = record.sale_order_ref.picking_ids
                
                # ถ้าไม่พบจาก picking_ids ให้ค้นหาจาก origin
                if not all_pickings:
                    all_pickings = self.env['stock.picking'].search([
                        ('origin', '=', record.sale_order_ref.name)
                    ])
                
                # กรองเฉพาะรายการที่ไม่ใช่ draft หรือ cancelled (แสดงทั้ง incoming และ outgoing)
                pickings = all_pickings.filtered(
                    lambda p: p.state not in ('draft', 'cancel')
                )
                
            elif record.partner_id:
                # กรณีมีแค่ customer แต่ไม่มี sale order - แสดงทุก type
                pickings = self.env['stock.picking'].search([
                    ('partner_id', '=', record.partner_id.id),
                    ('state', 'not in', ('draft', 'cancel'))
                ])
            
            record.delivery_ids = pickings

    @api.model
    def create_from_invoice(self, invoice_id):
        """สร้างธุรกรรม E-Tax จากใบแจ้งหนี้"""
        invoice = self.env['account.move'].browse(invoice_id)
        if not invoice:
            return False

        # หาการตั้งค่า E-Tax ที่ใช้งานอยู่
        etax_config = self.env['etax.config'].search([('active', '=', True)], limit=1)
        if not etax_config:
            raise ValueError('ไม่พบการตั้งค่า E-Tax ที่ใช้งานได้')

        if self.invoice_id.name:
            invoice = self.env['account.move'].search([('name', '=', self.invoice_id.name)], limit=1)

        if invoice.invoice_payment_term_id.line_ids:
            # ดึงรายการที่มี nb_days มากที่สุด
            payment_term_days = max(invoice.invoice_payment_term_id.line_ids.mapped('nb_days'))
        else:
            payment_term_days = 0
            
        calculated_due_date = invoice.invoice_date + timedelta(days=payment_term_days) if invoice.invoice_date else fields.Date.today()
        
        
        # สร้างธุรกรรมใหม่
        transaction = self.create({
            'document_id': invoice.name,
            'etax_config_id': etax_config.id,
            'partner_id': invoice.partner_id.id,
            'partner_tax_id': invoice.partner_id.vat or 'N/A',
            'partner_branch_id': invoice.partner_id.branch or '00000',
            'invoice_id': invoice.id or '',
            'document_date': invoice.invoice_date or fields.Date.today(),
            'payment_term': payment_term_days,   
            'payment_due_date': calculated_due_date,
            # 'payment_term': invoice.payment_term,   
            # 'payment_due_date': invoice.invoice_date_due or (fields.Date.today() + timedelta(days=30)),
            'amount_untaxed': invoice.amount_untaxed,
            'amount_tax': invoice.amount_tax,
            'amount_total': invoice.amount_total,
            'currency_id': invoice.currency_id.id,
        })
        
        # สร้างรายการสินค้า
        for line in invoice.invoice_line_ids.filtered(lambda l: not l.display_type):

            self.env['etax.transaction.line'].create({
                'transaction_id': transaction.id,
                'product_id': line.product_id.id,
                'name': line.name,
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'price_subtotal': line.price_subtotal,
                'tax_ids': [(6, 0, line.tax_ids.ids)],
            })
        
        return transaction

    def prepare_etax_data(self):
        """เตรียมข้อมูลสำหรับส่งไป E-Tax API"""
        self.ensure_one()

        currency_code = "THB"
        bank_name = ""
        cheque_no = ""
        date_str = ""
        branch = ""
        payment_method = ""

        invoice = self.invoice_id
        
        # เตรียมข้อมูลรายการสินค้า
        line_items = []
        for i, line in enumerate(self.line_ids, 1):
            tax_rate = 0
            tax_amount = 0
            if line.tax_ids:
                tax_rate = line.tax_ids[0].amount
                tax_amount = line.price_subtotal * (tax_rate / 100)
            
            line_item = {
                "L01-LINE_ID": str(i), # ลำดับ 
                "L02-PRODUCT_ID": line.product_id.default_code or '', # รหัสสินค้า
                "L03-PRODUCT_NAME": line.name[:100],  # รายการ
                "L04-PRODUCT_DESC": "", # รายการ
                "L05-PRODUCT_BATCH_ID": "",
                "L06-PRODUCT_EXPIRE_DTM": "",
                "L07-PRODUCT_CLASS_CODE": "",
                "L08-PRODUCT_CLASS_NAME": "",
                "L09-PRODUCT_ORIGIN_COUNTRY_ID": "",
                "L10-PRODUCT_CHARGE_AMOUNT": f"{line.price_unit:.2f}", # ราคาต่อหน่วย
                "L11-PRODUCT_CHARGE_CURRENCY_CODE": "THB",
                "L12-PRODUCT_ALLOWANCE_CHARGE_IND": "",
                "L13-PRODUCT_ALLOWANCE_ACTUAL_AMOUNT": "0.00",
                "L14-PRODUCT_ALLOWANCE_ACTUAL_CURRENCY_CODE": "THB",
                "L15-PRODUCT_ALLOWANCE_REASON_CODE": "",
                "L16-PRODUCT_ALLOWANCE_REASON": "",
                "L17-PRODUCT_QUANTITY": f"{abs(line.quantity):.2f}", # จำนวน
                "L18-PRODUCT_UNIT_CODE": "",
                "L19-PRODUCT_QUANTITY_PER_UNIT": "0.00",
                "L20-LINE_TAX_TYPE_CODE": "VAT",
                "L21-LINE_TAX_CAL_RATE": "0.00",
                "L22-LINE_BASIS_AMOUNT": "0.00",
                "L23-LINE_BASIS_CURRENCY_CODE": "THB",
                "L24-LINE_TAX_CAL_AMOUNT": "0.00",
                "L25-LINE_TAX_CAL_CURRENCY_CODE": "THB",
                "L26-LINE_ALLOWANCE_CHARGE_IND": "",
                "L27-LINE_ALLOWANCE_ACTUAL_AMOUNT": "0.00",
                "L28-LINE_ALLOWANCE_ACTUAL_CURRENCY_CODE": "",
                "L29-LINE_ALLOWANCE_REASON_CODE": "",
                "L30-LINE_ALLOWANCE_REASON": "",
                "L31-LINE_TAX_TOTAL_AMOUNT": "0.00",
                "L32-LINE_TAX_TOTAL_CURRENCY_CODE": "",
                "L33-LINE_NET_TOTAL_AMOUNT": f"{abs(line.price_subtotal):.2f}", # จำนวนเงิน
                "L34-LINE_NET_TOTAL_CURRENCY_CODE": "THB",
                "L35-LINE_NET_INCLUDE_TAX_TOTAL_AMOUNT": "0.00",
                "L36-LINE_NET_INCLUDE_TAX_TOTAL_CURRENCY_CODE": "THB",
            }
            
            # เพิ่มฟิลด์ Remark
            for j in range(37, 47):
                line_item[f"L{j:02d}-PRODUCT_REMARK{j-36}"] = ""
            
            line_items.append(line_item)

        dbn_label = dict(self._fields['remark_dbn'].selection).get(self.remark_dbn)
        cdn_label = dict(self._fields['remark_cdn'].selection).get(self.remark_cdn)
        doc_label = dict(self._fields['document_type'].selection).get(self.document_type)

        # ตรวจสอบว่ามีฟิลด์ที่ต้องการหรือไม่ และกำหนดค่าเริ่มต้น
        payment_method = ""
        bank_name = ""
        branch = ""
        cheque_no = ""
        date_str = ""
        
        # ใช้ฟิลด์ที่มีอยู่จริงใน account.move หรือกำหนดค่าเริ่มต้น
        if hasattr(invoice, 'cash_group_field1') and (invoice.cash_group_field1 or getattr(invoice, 'cash_group_field2', '')):
            payment_method = "เงินโอน"
            bank_name = invoice.cash_group_field1
            branch = getattr(invoice, 'cash_group_field2', '')
        elif hasattr(invoice, 'cheque_group_field1') and (getattr(invoice, 'cheque_group_field1', '') or getattr(invoice, 'cheque_group_field2', '')):
            payment_method = "เช็คธนาคาร"
            bank_name = getattr(invoice, 'cheque_group_field3', '')
            cheque_no = getattr(invoice, 'cheque_group_field1', '')
            date_str = getattr(invoice, 'cheque_group_field2', '')
        
        # ข้อมูลหลักสำหรับ API
        etax_data = {
            "SellerTaxId": self.etax_config_id.seller_tax_id,
            "SellerBranchId": self.etax_config_id.seller_branch_id,
            "APIKey": self.etax_config_id.api_key,
            "UserCode": self.etax_config_id.user_code,
            "AccessKey": self.etax_config_id.access_key,
            "ServiceCode": self.etax_config_id.service_code,
            "TextContent": {
                # ข้อมูลบริษัท
                "C01-SELLER_TAX_ID": self.etax_config_id.seller_tax_id, # เลขประจำตัวผู้เสียภาษีอากร
                "C02-SELLER_BRANCH_ID": self.etax_config_id.seller_branch_id, # รหัสสาขา
                "C03-FILE_NAME": "",
                
                # ข้อมูลเอกสาร
                "H01-DOCUMENT_TYPE_CODE": self.document_type,
                "H02-DOCUMENT_NAME": f"{doc_label}", # ชื่อเอกสาร
                "H03-DOCUMENT_ID": self.invoice_id.name or "", # เลขที่เอกสาร
                "H04-DOCUMENT_ISSUE_DTM": self.document_date.strftime("%Y-%m-%dT00:00:00"), # วันที่ออกเอกสาร
                "H05-CREATE_PURPOSE_CODE": (
                    self.remark_dbn if self.document_type == '80'
                    else self.remark_cdn if self.document_type == '81'
                    else ''
                ),  # เหตุผลในการเพิ่ม/ลดหนี้
                "H06-CREATE_PURPOSE": (
                    dbn_label if self.document_type == '80'
                    else cdn_label if self.document_type == '81'
                    else ''
                ), # เหตุผลในการเพิ่ม/ลดหนี้

                "H07-ADDITIONAL_REF_ASSIGN_ID": (self.selected_invoice_id.name if self.selected_invoice_id.name else self.invoice_id.name) if self.document_type in ('80', '81') else "", # อ้างอิงใบกำกับภาษีเดิม [CN, DN]
                "H08-ADDITIONAL_REF_ISSUE_DTM": (self.selected_invoice_id.invoice_date.strftime("%Y-%m-%dT00:00:00") if self.selected_invoice_id.name else self.invoice_id.invoice_date.strftime("%Y-%m-%dT00:00:00")) if self.document_type in ('80', '81') else "", # วันที่ใบกำกับภาษีเดิม [CN, DN]
                "H09-ADDITIONAL_REF_TYPE_CODE": self.document_type if self.document_type in ('80', '81') else "", # T03 = ว่าง
                "H10-ADDITIONAL_REF_DOCUMENT_NAME": "",
                "H11-DELIVERY_TYPE_CODE": "",
                "H12-BUYER_ORDER_ASSIGN_ID": f"{self.sale_order_ref.client_order_ref or ''}", #invoice.custom_reference or "", # self.sale_order_ref.name or "", # ใบสั่งซื้อเลขที่ [T03]
                # "H13-BUYER_ORDER_ISSUE_DTM": self.selected_delivery_id.name or "", # วันที่ใบสั่งซื้อ [T03]
                "H13-BUYER_ORDER_ISSUE_DTM": "",
                "H14-BUYER_ORDER_REF_TYPE_CODE": "",
                "H15-DOCUMENT_REMARK": self.selected_delivery_id.name or "", #self.notes, # หมายเหตุ [T03, CN, DN]
                "H16-VOUCHER_NO": "",
                "H17-SELLER_CONTACT_PERSON_NAME": "",
                "H18-SELLER_CONTACT_DEPARTMENT_NAME": "",
                "H19-SELLER_CONTACT_URIID": "",
                "H20-SELLER_CONTACT_PHONE_NO": "",
                "H21-FLEX_FIELD": "",
                "H22-SELLER_BRANCH_ID": "", # ที่อยู่บริษัท [T03, CN, DN]
                "H23-SOURCE_SYSTEM": "",
                "H24-ENCRYPT_PASSWORD": "",
                "H25-PDF_TEMPLATE_ID": (
                    'MOGAN-DN' if self.document_type == '80'
                    else 'MOGAN-CN' if self.document_type == '81'
                    else 'MOGAN-T03' if self.document_type == 'T03'
                    else ''
                ),
                "H26-SEND_MAIL_IND": self.etax_config_id.send_mail_ind,
                "H27-PDF_NAME": "",
                "H28-BARCODE_FOR_BANK": "",
                "H29-CP_RETURN_DOCUMENT_ID": "",
                "H30-SEND_XML_EMAIL": "",
                "H31-EPAYMENT_QRCODE": "",

                # ข้อมูลลูกค้า
                "B01-BUYER_ID": str(self.partner_id.id).zfill(6),
                "B02-BUYER_NAME": self.partner_id.name[:100], # ผู้ซื้อ
                "B03-BUYER_TAX_ID_TYPE": "OTHR" if not self.partner_id.vat or self.partner_id.vat == 'N/A' else "TXID",
                "B04-BUYER_TAX_ID": self.partner_id.vat or "N/A", # เลขประจำตัวผู้เสียภาษีอากร
                "B05-BUYER_BRANCH_ID": (self.partner_id.branch or "")[:5] if self.partner_id.branch else '00000', #self.partner_branch_id, # รหัสสาขาผู้ซื้อ
                "B06-BUYER_CONTACT_PERSON_NAME": "",
                "B07-BUYER_CONTACT_DEPARTMENT_NAME": "",
                "B08-BUYER_URIID": self.partner_id.email or "",
                "B09-BUYER_CONTACT_PHONE_NO": "",
                "B10-BUYER_POST_CODE": self.partner_id.zip or "", # รหัสไปรษณีย์ผู้ซื้อ [T03, CN, DN]
                "B11-BUYER_BUILDING_NAME": "",
                "B12-BUYER_BUILDING_NO": "",
                "B13-BUYER_ADDRESS_LINE1": (self.partner_id.street or "")[:200], # ที่อยู่ผู้ซื้อ [T03, CN, DN]
                "B14-BUYER_ADDRESS_LINE2": (
                        (self.partner_id.street2 or "") + " " + 
                        (self.partner_id.city or "") + " " + 
                        (self.partner_id.state_id.name if self.partner_id.state_id else "")
                    )[:200], # ที่อยู่ผู้ซื้อ [T03, CN, DN]
                "B15-BUYER_ADDRESS_LINE3": "",
                "B16-BUYER_ADDRESS_LINE4": "",
                "B17-BUYER_ADDRESS_LINE5": "",
                "B18-BUYER_STREET_NAME": "",
                "B19-BUYER_CITY_SUB_DIV_ID": "",
                "B20-BUYER_CITY_SUB_DIV_NAME": "",
                "B21-BUYER_CITY_ID": "",
                "B22-BUYER_CITY_NAME": "",
                "B23-BUYER_COUNTRY_SUB_DIV_ID": "",
                "B24-BUYER_COUNTRY_SUB_DIV_NAME": "",
                "B25-BUYER_COUNTRY_ID": "TH",
                
                # รายการสินค้า
                "LINE_ITEM_INFORMATION": line_items,
                
                # ข้อมูลสรุป
                "F01-LINE_TOTAL_COUNT": "0",
                "F02-DELIVERY_OCCUR_DTM": "",
                "F03-INVOICE_CURRENCY_CODE": currency_code,
                "F04-TAX_TYPE_CODE1": "VAT",
                "F05-TAX_CAL_RATE1": "0.00",
                "F06-BASIS_AMOUNT1": "0.00",
                "F07-BASIS_CURRENCY_CODE1": currency_code,
                "F08-TAX_CAL_AMOUNT1": "0.00",
                "F09-TAX_CAL_CURRENCY_CODE1": currency_code,
                "F10-TAX_TYPE_CODE2": "",
                "F11-TAX_CAL_RATE2": "",
                "F12-BASIS_AMOUNT2": "",
                "F13-BASIS_CURRENCY_CODE2": "",
                "F14-TAX_CAL_AMOUNT2": "",
                "F15-TAX_CAL_CURRENCY_CODE2": "",
                "F16-TAX_TYPE_CODE3": "",
                "F17-TAX_CAL_RATE3": "",
                "F18-BASIS_AMOUNT3": "",
                "F19-BASIS_CURRENCY_CODE3": "",
                "F20-TAX_CAL_AMOUNT3": "0.00",
                "F21-TAX_CAL_CURRENCY_CODE3": currency_code,
                "F22-TAX_TYPE_CODE4": "",
                "F23-TAX_CAL_RATE4": "",
                "F24-BASIS_AMOUNT4": "",
                "F25-BASIS_CURRENCY_CODE4": "",
                "F26-TAX_CAL_AMOUNT4": "",
                "F27-TAX_CAL_CURRENCY_CODE4": "",
                "F28-ALLOWANCE_CHARGE_IND": "false",
                "F29-ALLOWANCE_ACTUAL_AMOUNT": 
                (
                    f"{abs(self.amount_disc):.2f}" if self.document_type == 'T03'
                    else "0.00"
                ), # ส่วนลด [T03]
                "F30-ALLOWANCE_ACTUAL_CURRENCY_CODE": currency_code,
                "F31-ALLOWANCE_REASON_CODE": "",
                "F32-ALLOWANCE_REASON": "",
                "F33-PAYMENT_TYPE_CODE": "",
                "F34-PAYMENT_DESCRIPTION": "",
                "F35-PAYMENT_DUE_DTM": self.payment_due_date.strftime("%Y-%m-%dT00:00:00") if self.payment_due_date else "", # เครดิต/วันครบกำหนดชำระ
                "F36-ORIGINAL_TOTAL_AMOUNT": 
                (
                    f"{abs(self.original_amount):.2f}" if self.document_type in ['80', '81']
                    else f"{abs(self.amount_untaxed):.2f}"
                ), # มูลค่าตามใบกำกับภาษีเดิม [CN]
                "F37-ORIGINAL_TOTAL_CURRENCY_CODE": currency_code,
                "F38-LINE_TOTAL_AMOUNT": f"{abs(self.amount_untaxed):.2f}", # รวมจำนวนเงิน [T03], มุลค่าที่ถูกต้อง [CN]
                "F39-LINE_TOTAL_CURRENCY_CODE": currency_code,
                "F40-ADJUSTED_INFORMATION_AMOUNT": f"{abs(self.difference_amount):.2f}" or "0.00", # ผลต่าง [CN]
                "F41-ADJUSTED_INFORMATION_CURRENCY_CODE": currency_code,
                "F42-ALLOWANCE_TOTAL_AMOUNT": "0.00",
                "F43-ALLOWANCE_TOTAL_CURRENCY_CODE": currency_code,
                "F44-CHARGE_TOTAL_AMOUNT": "0.00",
                "F45-CHARGE_TOTAL_CURRENCY_CODE": "",
                "F46-TAX_BASIS_TOTAL_AMOUNT": f"{abs(self.total_after_deposit):.2f}", # มูลค่าที่นำมาคิดภาษี [T03]
                "F47-TAX_BASIS_TOTAL_CURRENCY_CODE": currency_code,
                "F48-TAX_TOTAL_AMOUNT": 
                (
                    f"{abs(self.amount_tax):.2f}" if self.document_type in ['80', '81']
                    else f"{abs(self.amount_vat):.2f}" if self.document_type == 'T03'
                    else "0.00"
                ), # รวมจำนวนเงิน [T03, CN, DN]
                "F49-TAX_TOTAL_CURRENCY_CODE": currency_code,
                "F50-GRAND_TOTAL_AMOUNT":
                (
                    f"{abs(self.amount_total):.2f}" if self.document_type in ['80', '81']
                    else f"{abs(self.net_amount_total):.2f}" if self.document_type == 'T03'
                    else "0.00"
                ), # รวมจำนวนเงิน [T03, CN, DN]
                "F51-GRAND_TOTAL_CURRENCY_CODE": currency_code,
                "F52-TERM_PAYMENT": f"{self.payment_term} วัน", # กำหนดชำระเงิน [CN, DN]
                "F53-WITHHOLDINGTAX_TYPE1": "",
                "F54-WITHHOLDINGTAX_DESCRIPTION1": "",
                "F55-WITHHOLDINGTAX_RATE1": "",
                "F56-WITHHOLDINGTAX_BASIS_AMOUNT1": "",
                "F57-WITHHOLDINGTAX_TAX_AMOUNT1": "",
                "F58-WITHHOLDINGTAX_TYPE2": "",
                "F59-WITHHOLDINGTAX_DESCRIPTION2": "",
                "F60-WITHHOLDINGTAX_RATE2": "",
                "F61-WITHHOLDINGTAX_BASIS_AMOUNT2": "",
                "F62-WITHHOLDINGTAX_TAX_AMOUNT2": "",
                "F63-WITHHOLDINGTAX_TYPE3": "",
                "F64-WITHHOLDINGTAX_DESCRIPTION3": "",
                "F65-WITHHOLDINGTAX_RATE3": "",
                "F66-WITHHOLDINGTAX_BASIS_AMOUNT3": "",
                "F67-WITHHOLDINGTAX_TAX_AMOUNT3": "",
                "F68-WITHHOLDINGTAX_TOTAL_AMOUNT": "0.00",
                "F69-ACTUAL_PAYMENT_TOTAL_AMOUNT": "0.00",
                "F70-DOCUMENT_REMARK1": self.notes, # หมายเหตุ [T03, CN, DN]
                "F71-DOCUMENT_REMARK2": 
                (
                    f"{abs(self.net_amount):.2f}" if self.document_type == 'T03'
                    else "0.00"
                ), # ยอดหลังหักส่วนลด [T03]

                "F72-DOCUMENT_REMARK3": self.partner_id.email or "",#self.partner_id.email or "", # อีเมลผู้ซื้อ [T03]
                "F73-DOCUMENT_REMARK4": "",
                "F74-DOCUMENT_REMARK5": "",
                "F75-DOCUMENT_REMARK6": "",
                "F76-DOCUMENT_REMARK7": "",
                "F77-DOCUMENT_REMARK8": "",
                "F78-DOCUMENT_REMARK9": "",
                "F79-DOCUMENT_REMARK10": "",
                "F80-DOCUMENT_REMARK11": "",
                "F80-DOCUMENT_REMARK12": "",
                "F80-DOCUMENT_REMARK13": "",
                "F80-DOCUMENT_REMARK14": "",
                "F80-DOCUMENT_REMARK15": "",
                "F80-DOCUMENT_REMARK16": "",
                "F80-DOCUMENT_REMARK17": "",
                "F80-DOCUMENT_REMARK18": "",
                "F80-DOCUMENT_REMARK19": "",
                "F80-DOCUMENT_REMARK20": "",
                "T01-TOTAL_DOCUMENT_COUNT": "1"
            },
            "PDFContent": ""
        }
        
        return etax_data

    def send_to_etax(self):
        """ส่งข้อมูลไปยัง E-Tax API"""
        self.ensure_one()

        etax_data = self.prepare_etax_data()
        # self.notes = json.dumps(etax_data, ensure_ascii=False, indent=2)
        try:
            self.state = 'sending'
            
            # ส่งข้อมูลไป API
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {self.etax_config_id.api_key}"
            }

            response = requests.post(
                self.etax_config_id.api_url,
                data=json.dumps(etax_data),
                headers=headers,
                timeout=30
            )
            
            # บันทึกการตอบกลับ
            self.api_response = response.text
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status') == 'OK':
                    # อัพเดทข้อมูลเมื่อสำเร็จ
                    self.write({
                        'state': 'sent',
                        'transaction_code': result.get('transactionCode'),
                        'pdf_url': result.get('pdfURL'),
                        'xml_url': result.get('xmlURL'),
                        'error_message': '',
                    })
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'สำเร็จ!',
                            'message': f'ส่งข้อมูลไปยัง E-Tax สำเร็จ\nรหัสธุรกรรม: {result.get("transactionCode")}',
                            'type': 'success',
                            'sticky': False,
                            'next': {
                                'type': 'ir.actions.client',
                                'tag': 'reload',
                            }
                        }
                    }
                else:
                    # มีข้อผิดพลาดจาก API
                    self.write({
                        'state': 'error',
                        'error_message': result.get('message', 'ไม่ทราบสาเหตุ'),
                    })
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'ข้อผิดพลาด 01!',
                            'message': f'E-Tax API Error: {result.get("message", etax_data)}',
                            'type': 'warning',
                        }
                    }
            else:
                # HTTP Error
                self.write({
                    'state': 'error',
                    'error_message': f'HTTP Error {response.status_code}: {response.text}',
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'ข้อผิดพลาด 02!',
                        'message': f'HTTP Error {response.status_code}',
                        'type': 'danger',
                    }
                }
                
        except Exception as e:
            _logger.error(f"E-Tax Send Error: {str(e)}")
            self.write({
                'state': 'error',
                'error_message': str(e),
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'ข้อผิดพลาด 03!',
                    'message': f'เกิดข้อผิดพลาด 04: {str(etax_data)}',
                    'type': 'danger',
                }
            }

    def action_download_pdf(self):
        """ดาวน์โหลดไฟล์ PDF"""
        if self.pdf_url:
            return {
                'type': 'ir.actions.act_url',
                'url': self.pdf_url,
                'target': 'new',
            }

    def action_download_xml(self):
        """ดาวน์โหลดไฟล์ XML"""
        if self.xml_url:
            return {
                'type': 'ir.actions.act_url',
                'url': self.xml_url,
                'target': 'new',
            }

    @api.depends('line_ids.price_subtotal', 'original_amount')
    def _compute_difference_amount(self):
        for record in self:
            if record.document_type in ['81', '80']:
                record.difference_amount = sum(line.price_subtotal for line in record.line_ids)
            elif record.document_type in ['T03']:
                line_total = sum(line.price_subtotal for line in record.line_ids)
                record.difference_amount = abs((record.original_amount or 0.0) - line_total)
            else:
                record.difference_amount = 0.0

    @api.depends('line_ids.price_subtotal', 'original_amount', 'difference_amount')
    def _compute_amount_untaxed(self):
        for record in self:
            total = 0.0
            if record.document_type in ['T03']:
                total = sum(line.price_subtotal for line in record.line_ids)
            elif record.document_type in ['81']:
                total = abs((record.original_amount or 0.0) - (record.difference_amount or 0.0))
            elif record.document_type in ['80']: # เพิ่มหนี้
                total = abs((record.original_amount or 0.0) + (record.difference_amount or 0.0))
            
            record.amount_untaxed = total
    
    def _compute_amount_cur(self):
        for record in self:
            record.amount_cur = sum(line.price_subtotal for line in record.line_ids)

    @api.depends('line_ids.price_subtotal', 'original_amount', 'amount_untaxed')
    def _compute_amount_tax(self):
        for record in self:
            total_tax = sum(line.price_tax for line in record.line_ids)

            if total_tax > 0: # ตรวจสอบว่ามีภาษีหรือไม่
                total_tax = abs(record.difference_amount or 0.0) * 7 / 100  # สมมติอัตราภาษี 7%
            else :
                total_tax = 0

            record.amount_tax = total_tax

            # invoice = self.env['account.move'].search([('name', '=', record.journal_entry_memo)], limit=1)
            # record.amount_tax = invoice.amount_tax if invoice.amount_tax else 0.0

            # if record.document_type in ['T03']:
            #     total = abs((record.original_amount or 0.0) - (record.amount_untaxed or 0.0))
            # elif record.document_type in ['81', '80']:
            #     total = sum(line.price_subtotal for line in record.line_ids)
            # else:
            #     total = 0.0

            # record.amount_tax = (total or 0.0) * 7 / 100
    
    @api.depends('line_ids.price_subtotal', 'original_amount', 'amount_untaxed')
    def _compute_net_amount_tax(self):
        for record in self:
            # คำนวณภาษีจากรายการสินค้าโดยตรง (ใช้ค่าจาก tax_ids ที่เลือกจริง)
            total_tax = sum(line.price_tax for line in record.line_ids) 

            if total_tax > 0: # ตรวจสอบว่ามีภาษีหรือไม่
                total_tax = abs(record.total_after_deposit or 0.0) * 7 / 100  # สมมติอัตราภาษี 7%
            else :
                total_tax = 0

            record.amount_vat = total_tax

            # if record.document_type in ['T03']:
            #     total = abs((record.original_amount or 0.0) - (record.amount_untaxed or 0.0))
            # elif record.document_type in ['81', '80']:
            #     total = sum(line.price_subtotal for line in record.line_ids)
            # else:
            #     total = 0.0

            # record.amount_vat = (total or 0.0) * 7 / 100

    @api.depends('line_ids.price_subtotal', 'original_amount', 'amount_untaxed', 'amount_tax')
    def _compute_amount_total(self):
        for record in self:
            if record.document_type in ['T03']:
                total = abs((record.original_amount or 0.0) - (record.amount_untaxed or 0.0))
            elif record.document_type in ['81', '80']:
                total = sum(line.price_subtotal for line in record.line_ids)
            else:
                total = 0.0

            record.amount_total = (total or 0.0) + (record.amount_tax or 0.0)

    @api.depends('total_after_deposit', 'amount_vat')
    def _compute_net_amount_total(self):
        for record in self:
            record.net_amount_total = (record.total_after_deposit or 0.0) + (record.amount_vat or 0.0)

    @api.depends('invoice_id.amount_untaxed')
    def _compute_original_amount(self):
        for record in self:
            invoice = record.selected_invoice_id if record.selected_invoice_id else False
            record.original_amount = invoice.amount_untaxed if invoice and invoice.amount_untaxed else 0.0

    @api.depends('line_ids.price_unit', 'line_ids.quantity', 'line_ids.discount')
    def _compute_amount_disc(self):
        for record in self:
            # total_disc = 0.0
            # for line in record.line_ids:
            #     # discount เป็นเปอร์เซ็นต์ เช่น 10 หมายถึง 10%
            #     line_disc = (line.price_unit * line.quantity) * (line.discount / 100.0)
            #     total_disc += line_disc
            # record.amount_disc = total_disc
            record.amount_disc = 0 #WK#1.n 20260624

    @api.depends('amount_untaxed', 'amount_disc')
    def _compute_net_amount(self):
        for record in self:
            record.net_amount = record.amount_untaxed - (record.amount_disc or 0.0)
            # ผลลัพธ์คือ มูลค่าที่ถูกต้อง (amount_untaxed) - ส่วนลด (amount_disc)

    @api.depends('net_amount', 'deposit')
    def _compute_total_after_deposit(self):
        for record in self:
            record.total_after_deposit = (record.amount_untaxed or 0.0) - (record.amount_disc or 0.0)
            # record.total_after_deposit = (record.net_amount or 0.0) - (record.deposit or 0.0)

    @api.depends('document_type', 'amount_total', 'net_amount_total')
    def _compute_invoice_total(self):
        for record in self:
            if record.document_type in ['81', '80']:
                record.invoice_total = record.amount_total
            elif record.document_type in ['T03']:
                record.invoice_total = record.net_amount_total
            else:
                record.invoice_total = 0.0
    
    def _compute_journal_entry_info(self):
        """
        คำนวณและดึงข้อมูล Journal Entry Info จาก invoice ที่เชื่อมโยง
        """
        for record in self:
            # รีเซ็ตค่าเริ่มต้น
            record.journal_entry_memo = ''
            
            # ตรวจสอบว่ามี invoice เชื่อมโยงหรือไม่
            if record.invoice_id:
                # invoice = env['account.move'].browse(record.invoice_id)

                # ดึงข้อมูลที่ต้องการ
                # record.journal_entry_memo = invoice.ref
                # ดึงเฉพาะหมายเลขเอกสารจาก ref (ตัด "Reversal of: " ออก)
                ref_value = record.invoice_id.ref or ''
                if ref_value.startswith('Reversal of: '):
                    # ตัดคำว่า "Reversal of: " ออกและแยกเอาแค่หมายเลขแรก
                    ref_value = ref_value.replace('Reversal of: ', '').split(',')[0].strip()
                record.journal_entry_memo = ref_value
                # record.journal_entry_memo = record.invoice_id.invoice_origin or 'Test2'


class EtaxTransactionLine(models.Model):
    _name = 'etax.transaction.line'
    _description = 'รายการสินค้า E-Tax'

    transaction_id = fields.Many2one('etax.transaction', 'ธุรกรรม', required=True, ondelete='cascade')
    sequence = fields.Integer('ลำดับ', default=10)
    
    product_id = fields.Many2one('product.product', 'สินค้า')
    name = fields.Char('รายละเอียด', related='product_id.name', readonly=True)
    service_policy = fields.Char('Service Policy', help='Service policy from product (e.g., ordered_prepaid, delivered_timesheet)')
    invoice_policy = fields.Char('Invoice Policy', help='Invoice policy from product (e.g., order, delivery)')

    quantity = fields.Float('จำนวน', default=1.0)
    discount = fields.Float('ส่วนลด (%)', default=0.0)
    uom_id = fields.Many2one('uom.uom', 'หน่วย')
    product_name = fields.Char('ชื่อสินค้า', related='product_id.name', readonly=True)
    price_unit = fields.Float('ราคาต่อหน่วย')
    price_subtotal = fields.Float('ราคารวม', compute='_compute_price_subtotal')

    price_tax = fields.Float('ภาษี', compute='_compute_price_tax')
    price_total = fields.Float('รวมทั้งหมด', compute='_compute_price_total')
    
    tax_ids = fields.Many2many('account.tax', 'etax_line_tax_rel', 'line_id', 'tax_id', 'ภาษี')

    @api.depends('quantity', 'price_unit', 'discount')
    def _compute_price_subtotal(self):
        for line in self:
            subtotal = line.quantity * line.price_unit
            if line.discount:
                subtotal = subtotal * (1 - line.discount / 100.0)
            line.price_subtotal = subtotal
    
    @api.depends('price_subtotal', 'tax_ids')
    def _compute_price_tax(self):
        for line in self:
            tax_amount = 0.0
            if line.tax_ids:
                # คำนวณภาษีจาก tax_ids
                for tax in line.tax_ids:
                    if tax.amount_type == 'percent':
                        tax_amount += line.price_subtotal * (tax.amount / 100.0)
            line.price_tax = tax_amount
    
    @api.depends('price_subtotal', 'price_tax')
    def _compute_price_total(self):
        for line in self:
            line.price_total = line.price_subtotal + line.price_tax
    
    # def _compute_price_subtotal(self):
    #     for line in self:
    #         line.price_subtotal = line.quantity * line.price_unit

