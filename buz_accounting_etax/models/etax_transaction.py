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
        ('T04', 'ใบแจ้งหนี้/ใบกำกับภาษี'),
        ('380', 'ใบแจ้งหนี้'),
        ('81', 'ใบลดหนี้'),
        ('80', 'ใบเพิ่มหนี้'),
    ], 'ประเภทเอกสาร', default='T04', required=True)
    
    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('sending', 'กำลังส่ง'),
        ('sent', 'ส่งสำเร็จ'),
        ('error', 'ข้อผิดพลาด'),
    ], 'สถานะ', default='draft')
    
    # ข้อมูล API
    etax_config_id = fields.Many2one('etax.config', 'การตั้งค่า E-Tax', required=False)
    transaction_code = fields.Char('รหัสธุรกรรม E-Tax', readonly=True)
    
    # ข้อมูลลูกค้า
    partner_id = fields.Many2one('res.partner', 'ลูกค้า', required=True)
    partner_tax_id = fields.Char('เลขประจำตัวผู้เสียภาษีลูกค้า')
    partner_branch_id = fields.Char('รหัสสาขาลูกค้า', default='00000')
    
    # ข้อมูลเอกสาร
    invoice_id = fields.Many2one('account.move', 'ใบแจ้งหนี้อ้างอิง')

    sale_order_ref = fields.Many2one('sale.order', 'ใบสั่งขายอ้างอิง')
    
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
        
        # สร้างธุรกรรมใหม่
        transaction = self.create({
            'document_id': invoice.name,
            'etax_config_id': etax_config.id,
            'partner_id': invoice.partner_id.id,
            'partner_tax_id': invoice.partner_id.vat or 'N/A',
            'invoice_id': invoice.id or '',
            'document_date': invoice.invoice_date or fields.Date.today(),
            'payment_term': invoice.payment_term,   
            'payment_due_date': invoice.invoice_date_due or (fields.Date.today() + timedelta(days=30)),
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
                "L01-LINE_ID": str(i),
                "L02-PRODUCT_ID": line.product_id.default_code or '',
                "L03-PRODUCT_NAME": line.name[:100],  # จำกัดความยาว
                "L04-PRODUCT_DESC": "",
                "L05-PRODUCT_BATCH_ID": "",
                "L06-PRODUCT_EXPIRE_DTM": "",
                "L07-PRODUCT_CLASS_CODE": "",
                "L08-PRODUCT_CLASS_NAME": "",
                "L09-PRODUCT_ORIGIN_COUNTRY_ID": "",
                "L10-PRODUCT_CHARGE_AMOUNT": f"{line.price_unit:.2f}",
                "L11-PRODUCT_CHARGE_CURRENCY_CODE": "THB",
                "L12-PRODUCT_ALLOWANCE_CHARGE_IND": "",
                "L13-PRODUCT_ALLOWANCE_ACTUAL_AMOUNT": "0.00",
                "L14-PRODUCT_ALLOWANCE_ACTUAL_CURRENCY_CODE": "THB",
                "L15-PRODUCT_ALLOWANCE_REASON_CODE": "",
                "L16-PRODUCT_ALLOWANCE_REASON": "",
                "L17-PRODUCT_QUANTITY": f"{line.quantity:.2f}",
                "L18-PRODUCT_UNIT_CODE": "",
                "L19-PRODUCT_QUANTITY_PER_UNIT": f"{line.price_unit:.2f}",
                "L20-LINE_TAX_TYPE_CODE": "VAT",
                "L21-LINE_TAX_CAL_RATE": f"{tax_rate:.2f}",
                "L22-LINE_BASIS_AMOUNT": f"{line.price_subtotal:.2f}",
                "L23-LINE_BASIS_CURRENCY_CODE": "THB",
                "L24-LINE_TAX_CAL_AMOUNT": f"{tax_amount:.2f}",
                "L25-LINE_TAX_CAL_CURRENCY_CODE": "THB",
                "L26-LINE_ALLOWANCE_CHARGE_IND": "",
                "L27-LINE_ALLOWANCE_ACTUAL_AMOUNT": "0.00",
                "L28-LINE_ALLOWANCE_ACTUAL_CURRENCY_CODE": "",
                "L29-LINE_ALLOWANCE_REASON_CODE": "",
                "L30-LINE_ALLOWANCE_REASON": "",
                "L31-LINE_TAX_TOTAL_AMOUNT": "0.00",
                "L32-LINE_TAX_TOTAL_CURRENCY_CODE": "",
                "L33-LINE_NET_TOTAL_AMOUNT": f"{line.price_subtotal:.2f}",
                "L34-LINE_NET_TOTAL_CURRENCY_CODE": "THB",
                "L35-LINE_NET_INCLUDE_TAX_TOTAL_AMOUNT": f"{line.price_subtotal:.2f}",
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
                "C01-SELLER_TAX_ID": self.etax_config_id.seller_tax_id,
                "C02-SELLER_BRANCH_ID": self.etax_config_id.seller_branch_id,
                "C03-FILE_NAME": "",
                
                # ข้อมูลเอกสาร
                "H01-DOCUMENT_TYPE_CODE": self.document_type,
                "H02-DOCUMENT_NAME": f"{doc_label}",
                "H03-DOCUMENT_ID": self.invoice_id.name or "",
                "H04-DOCUMENT_ISSUE_DTM": self.document_date.strftime("%Y-%m-%dT00:00:00"),
                "H05-CREATE_PURPOSE_CODE": (
                    self.remark_dbn if self.document_type == '80'
                    else self.remark_cdn if self.document_type == '81'
                    else ''
                ),
                "H06-CREATE_PURPOSE": (
                    dbn_label if self.document_type == '80'
                    else cdn_label if self.document_type == '81'
                    else ''
                ),
                "H07-ADDITIONAL_REF_ASSIGN_ID": self.invoice_id.name or "",
                "H08-ADDITIONAL_REF_ISSUE_DTM": self.document_date.strftime("%Y-%m-%dT00:00:00"),
                "H09-ADDITIONAL_REF_TYPE_CODE": self.document_type,
                "H10-ADDITIONAL_REF_DOCUMENT_NAME": "",
                "H11-DELIVERY_TYPE_CODE": "",
                "H12-BUYER_ORDER_ASSIGN_ID": self.sale_order_ref.name or "",
                "H13-BUYER_ORDER_ISSUE_DTM": "",
                "H14-BUYER_ORDER_REF_TYPE_CODE": "",
                "H15-DOCUMENT_REMARK": "", #self.notes, # หมายเหตุ
                "H16-VOUCHER_NO": "",
                "H17-SELLER_CONTACT_PERSON_NAME": "",
                "H18-SELLER_CONTACT_DEPARTMENT_NAME": "",
                "H19-SELLER_CONTACT_URIID": "",
                "H20-SELLER_CONTACT_PHONE_NO": "",
                "H21-FLEX_FIELD": "",
                "H22-SELLER_BRANCH_ID": "",
                "H23-SOURCE_SYSTEM": "",
                "H24-ENCRYPT_PASSWORD": "",
                "H25-PDF_TEMPLATE_ID": self.etax_config_id.pdf_template_id,
                "H26-SEND_MAIL_IND": self.etax_config_id.send_mail_ind,
                "H27-PDF_NAME": "",
                
                # ข้อมูลลูกค้า
                "B01-BUYER_ID": str(self.partner_id.id).zfill(6),
                "B02-BUYER_NAME": self.partner_id.name[:100],
                "B03-BUYER_TAX_ID_TYPE": "OTHR" if not self.partner_id.vat or self.partner_id.vat == 'N/A' else "TXID",
                "B04-BUYER_TAX_ID": self.partner_id.vat or "N/A",
                "B05-BUYER_BRANCH_ID": self.partner_branch_id,
                "B08-BUYER_URIID": self.partner_id.email or "",
                "B10-BUYER_POST_CODE": self.partner_id.zip or "",
                "B13-BUYER_ADDRESS_LINE1": (self.partner_id.street or "")[:200],
                "B25-BUYER_COUNTRY_ID": "TH",
                
                # รายการสินค้า
                "LINE_ITEM_INFORMATION": line_items,
                
                # ข้อมูลสรุป
                "F01-LINE_TOTAL_COUNT": "0",
                "F02-DELIVERY_OCCUR_DTM": "",
                "F03-INVOICE_CURRENCY_CODE": currency_code,
                "F04-TAX_TYPE_CODE1": "VAT",
                "F05-TAX_CAL_RATE1": "7.00",
                "F06-BASIS_AMOUNT1": "0.00",
                "F07-BASIS_CURRENCY_CODE1": currency_code,
                "F08-TAX_CAL_AMOUNT1": f"{abs(self.amount_tax):.2f}",
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
                "F20-TAX_CAL_AMOUNT3": "",
                "F21-TAX_CAL_CURRENCY_CODE3": "",
                "F22-TAX_TYPE_CODE4": "",
                "F23-TAX_CAL_RATE4": "",
                "F24-BASIS_AMOUNT4": "",
                "F25-BASIS_CURRENCY_CODE4": "",
                "F26-TAX_CAL_AMOUNT4": "",
                "F27-TAX_CAL_CURRENCY_CODE4": "",
                "F28-ALLOWANCE_CHARGE_IND": "false",
                "F29-ALLOWANCE_ACTUAL_AMOUNT": "0.00",
                "F30-ALLOWANCE_ACTUAL_CURRENCY_CODE": currency_code,
                "F31-ALLOWANCE_REASON_CODE": "",
                "F32-ALLOWANCE_REASON": "",
                "F33-PAYMENT_TYPE_CODE": "",
                "F34-PAYMENT_DESCRIPTION": "",
                "F35-PAYMENT_DUE_DTM": self.payment_due_date.strftime("%Y-%m-%dT00:00:00") if self.payment_due_date else "",
                "F36-ORIGINAL_TOTAL_AMOUNT": "0.00",
                "F37-ORIGINAL_TOTAL_CURRENCY_CODE": currency_code,
                "F38-LINE_TOTAL_AMOUNT": f"{abs(self.amount_untaxed):.2f}",
                "F39-LINE_TOTAL_CURRENCY_CODE": currency_code,
                "F40-ADJUSTED_INFORMATION_AMOUNT": "0.00",
                "F41-ADJUSTED_INFORMATION_CURRENCY_CODE": currency_code,
                "F42-ALLOWANCE_TOTAL_AMOUNT": "0.00",
                "F43-ALLOWANCE_TOTAL_CURRENCY_CODE": currency_code,
                "F44-CHARGE_TOTAL_AMOUNT": "0.00",
                "F45-CHARGE_TOTAL_CURRENCY_CODE": "",
                "F46-TAX_BASIS_TOTAL_AMOUNT": f"{abs(self.total_after_deposit):.2f}",
                "F47-TAX_BASIS_TOTAL_CURRENCY_CODE": currency_code,
                "F48-TAX_TOTAL_AMOUNT": f"{abs(self.amount_tax):.2f}",
                "F49-TAX_TOTAL_CURRENCY_CODE": currency_code,
                "F50-GRAND_TOTAL_AMOUNT":
                (
                    f"{abs(self.amount_total):.2f}" if self.document_type in ['80', '81']
                    else f"{abs(self.net_amount_total):.2f}" if self.document_type == 'T04'
                    else "0.00"
                ),
                "F51-GRAND_TOTAL_CURRENCY_CODE": currency_code,
                "F52-TERM_PAYMENT": f"{self.payment_term} วัน",
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
                "F70-DOCUMENT_REMARK1": 
                (
                    f"{abs(self.amount_disc):.2f}" if self.document_type == 'T04'
                    else "0.00"
                ),
                "F71-DOCUMENT_REMARK2": 
                (
                    f"{abs(self.net_amount):.2f}" if self.document_type == 'T04'
                    else "0.00"
                ), # ยอดหลังหักส่วนลด

                "F72-DOCUMENT_REMARK3": f"{abs(self.deposit):.2f}",
                "F73-DOCUMENT_REMARK4": bank_name if payment_method == "เงินโอน" else "",
                "F74-DOCUMENT_REMARK5": date_str.strftime("%Y-%m-%d") if payment_method == "เงินโอน" else "",
                "F75-DOCUMENT_REMARK6": bank_name if payment_method == "เช็คธนาคาร" else "",
                "F76-DOCUMENT_REMARK7": cheque_no,
                "F77-DOCUMENT_REMARK8": date_str.strftime("%Y-%m-%d") if payment_method == "เช็คธนาคาร" else "",
                "F78-DOCUMENT_REMARK9": "",
                "F79-DOCUMENT_REMARK10": "",
                "T01-TOTAL_DOCUMENT_COUNT": "1"
            },
            "PDFContent": ""
        }
        
        return etax_data

    def send_to_etax(self):
        """ส่งข้อมูลไปยัง E-Tax API"""
        self.ensure_one()

        etax_data = self.prepare_etax_data()
        self.notes = json.dumps(etax_data, ensure_ascii=False, indent=2)
        try:
            self.state = 'sending'
            
            # เตรียมข้อมูล
            
            # self.notes = json.dumps(etax_data, ensure_ascii=False, indent=2)
            # etax_data = {
            #     "SellerTaxId": "0745534000876",
            #     "SellerBranchId": "00000",
            #     "APIKey": "Mjc6R29DY1JvRlA5RGc5QUhlNWh6aU15MUxvRHFwM1RJNXpTVTVrVUVTRTpleUowWVhocFpDSTZJakEzTkRVMU16UXdNREE0TnpZaUxDSndZWE56ZDI5eVpDSTZJbk4wWVhKQWNHRnpjekF4SW4wQVhKUEZUbVNVYk4xZ0V2WWE1TUxsZGpYR3BXNHdwUHo=",
            #     "UserCode": "starmarktest",
            #     "AccessKey": "star@pass01",
            #     "ServiceCode": "S03",
            #     "TextContent": {
            #         "C01-SELLER_TAX_ID": "0745534000876",
            #         "C02-SELLER_BRANCH_ID": "00000",
            #         "C03-FILE_NAME": "",
            #         "H01-DOCUMENT_TYPE_CODE": "T04",
            #         "H02-DOCUMENT_NAME": "ใบส่งของ/ใบกำกับภาษี",
            #         "H03-DOCUMENT_ID": "IV670600204",
            #         "H04-DOCUMENT_ISSUE_DTM": "2025-01-22T00:00:00",
            #         "H05-CREATE_PURPOSE_CODE": "",
            #         "H06-CREATE_PURPOSE": "",
            #         "H07-ADDITIONAL_REF_ASSIGN_ID": "",
            #         "H08-ADDITIONAL_REF_ISSUE_DTM": "",
            #         "H09-ADDITIONAL_REF_TYPE_CODE": "",
            #         "H10-ADDITIONAL_REF_DOCUMENT_NAME": "",
            #         "H11-DELIVERY_TYPE_CODE": "",
            #         "H12-BUYER_ORDER_ASSIGN_ID": "11",
            #         "H13-BUYER_ORDER_ISSUE_DTM": "",
            #         "H14-BUYER_ORDER_REF_TYPE_CODE": "",
            #         "H15-DOCUMENT_REMARK": "MANTANA ณ ราชพฤกษ์ 33",
            #         "H16-VOUCHER_NO": "",
            #         "H17-SELLER_CONTACT_PERSON_NAME": "",
            #         "H18-SELLER_CONTACT_DEPARTMENT_NAME": "",
            #         "H19-SELLER_CONTACT_URIID": "",
            #         "H20-SELLER_CONTACT_PHONE_NO": "",
            #         "H21-FLEX_FIELD": "",
            #         "H22-SELLER_BRANCH_ID": "",
            #         "H23-SOURCE_SYSTEM": "",
            #         "H24-ENCRYPT_PASSWORD": "",
            #         "H25-PDF_TEMPLATE_ID": "smm_T04",
            #         "H26-SEND_MAIL_IND": "Y",
            #         "H27-PDF_NAME": "",
            #         "B01-BUYER_ID": "000001",
            #         "B02-BUYER_NAME": "บริษัท สตาร์มาร์ค กรุ๊ป จำกัด",
            #         "B03-BUYER_TAX_ID_TYPE": "OTHR",
            #         "B04-BUYER_TAX_ID": "N/A",
            #         "B05-BUYER_BRANCH_ID": "00000",
            #         "B06-BUYER_CONTACT_PERSON_NAME": "",
            #         "B07-BUYER_CONTACT_DEPARTMENT_NAME": "",
            #         "B08-BUYER_URIID": "e-tax@starmark.co.th",
            #         "B09-BUYER_CONTACT_PHONE_NO": "",
            #         "B10-BUYER_POST_CODE": "10170",
            #         "B11-BUYER_BUILDING_NAME": "",
            #         "B12-BUYER_BUILDING_NO": "",
            #         "B13-BUYER_ADDRESS_LINE1": "27/8 หมู่ที่ 8 ถ.บรมราชชนนี แขวงฉิมพลี   เขตตลิ่งชัน จังหวัดกรุงเทพมหานคร",
            #         "B14-BUYER_ADDRESS_LINE2": "",
            #         "B15-BUYER_ADDRESS_LINE3": "",
            #         "B16-BUYER_ADDRESS_LINE4": "",
            #         "B17-BUYER_ADDRESS_LINE5": "",
            #         "B18-BUYER_STREET_NAME": "",
            #         "B19-BUYER_CITY_SUB_DIV_ID": "",
            #         "B20-BUYER_CITY_SUB_DIV_NAME": "",
            #         "B21-BUYER_CITY_ID": "",
            #         "B22-BUYER_CITY_NAME": "",
            #         "B23-BUYER_COUNTRY_SUB_DIV_ID": "",
            #         "B24-BUYER_COUNTRY_SUB_DIV_NAME": "",
            #         "B25-BUYER_COUNTRY_ID": "TH",
            #         "O01-SHIP_TO_ID": "",
            #         "O02-SHIP_TO_NAME": "",
            #         "O03-SHIP_TO_TAX_ID_TYPE": "",
            #         "O04-SHIP_TO_TAX_ID": "",
            #         "O05-SHIP_TO_BRANCH_ID": "",
            #         "O06-SHIP_TO_CONTACT_PERSON_NAME": "",
            #         "O07-SHIP_TO_CONTACT_DEPARTMENT_NAME": "",
            #         "O08-SHIP_TO_URIID": "",
            #         "O09-SHIP_TO_PHONE_NO": "",
            #         "O10-SHIP_TO_POST_CODE": "",
            #         "O11-SHIP_TO_BUILDING_NAME": "",
            #         "O12-SHIP_TO_BUILDING_NO": "",
            #         "O13-SHIP_TO_ADDRESS_LINE1": "",
            #         "O14-SHIP_TO_ADDRESS_LINE2": "",
            #         "O15-SHIP_TO_ADDRESS_LINE3": "",
            #         "O16-SHIP_TO_ADDRESS_LINE4": "",
            #         "O17-SHIP_TO_ADDRESS_LINE5": "",
            #         "O18-SHIP_TO_STREET_NAME": "",
            #         "O19-SHIP_TO_CITY_SUB_DIV_ID": "",
            #         "O20-SHIP_TO_CITY_SUB_DIV_NAME": "",
            #         "O21-SHIP_TO_CITY_ID": "",
            #         "O22-SHIP_TO_CITY_NAME": "",
            #         "O23-SHIP_TO_COUNTRY_SUB_DIV_ID": "",
            #         "O24-SHIP_TO_COUNTRY_SUB_DIV_NAME": "",
            #         "O25-SHIP_TO_COUNTRY_ID": "",
            #         "LINE_ITEM_INFORMATION": [
            #             {
            #                 "L01-LINE_ID": "1",
            #                 "L02-PRODUCT_ID": "PJ67-000004",
            #                 "L03-PRODUCT_NAME": "On2  5% ห้อง 00F08",
            #                 "L04-PRODUCT_DESC": "",
            #                 "L05-PRODUCT_BATCH_ID": "",
            #                 "L06-PRODUCT_EXPIRE_DTM": "",
            #                 "L07-PRODUCT_CLASS_CODE": "",
            #                 "L08-PRODUCT_CLASS_NAME": "",
            #                 "L09-PRODUCT_ORIGIN_COUNTRY_ID": "",
            #                 "L10-PRODUCT_CHARGE_AMOUNT": "625.00",
            #                 "L11-PRODUCT_CHARGE_CURRENCY_CODE": "THB",
            #                 "L12-PRODUCT_ALLOWANCE_CHARGE_IND": "",
            #                 "L13-PRODUCT_ALLOWANCE_ACTUAL_AMOUNT": "0.00",
            #                 "L14-PRODUCT_ALLOWANCE_ACTUAL_CURRENCY_CODE": "THB",
            #                 "L15-PRODUCT_ALLOWANCE_REASON_CODE": "",
            #                 "L16-PRODUCT_ALLOWANCE_REASON": "",
            #                 "L17-PRODUCT_QUANTITY": "1.00",
            #                 "L18-PRODUCT_UNIT_CODE": "",
            #                 "L19-PRODUCT_QUANTITY_PER_UNIT": "625.00",
            #                 "L20-LINE_TAX_TYPE_CODE": "VAT",
            #                 "L21-LINE_TAX_CAL_RATE": "7.00",
            #                 "L22-LINE_BASIS_AMOUNT": "625.00",
            #                 "L23-LINE_BASIS_CURRENCY_CODE": "THB",
            #                 "L24-LINE_TAX_CAL_AMOUNT": "43.75",
            #                 "L25-LINE_TAX_CAL_CURRENCY_CODE": "THB",
            #                 "L26-LINE_ALLOWANCE_CHARGE_IND": "",
            #                 "L27-LINE_ALLOWANCE_ACTUAL_AMOUNT": "0.00",
            #                 "L28-LINE_ALLOWANCE_ACTUAL_CURRENCY_CODE": "",
            #                 "L29-LINE_ALLOWANCE_REASON_CODE": "",
            #                 "L30-LINE_ALLOWANCE_REASON": "",
            #                 "L31-LINE_TAX_TOTAL_AMOUNT": "0.00",
            #                 "L32-LINE_TAX_TOTAL_CURRENCY_CODE": "",
            #                 "L33-LINE_NET_TOTAL_AMOUNT": "625.00",
            #                 "L34-LINE_NET_TOTAL_CURRENCY_CODE": "THB",
            #                 "L35-LINE_NET_INCLUDE_TAX_TOTAL_AMOUNT": "625.00",
            #                 "L36-LINE_NET_INCLUDE_TAX_TOTAL_CURRENCY_CODE": "THB",
            #                 "L37-PRODUCT_REMARK1": "33",
            #                 "L38-PRODUCT_REMARK2": "",
            #                 "L39-PRODUCT_REMARK3": "",
            #                 "L40-PRODUCT_REMARK4": "",
            #                 "L41-PRODUCT_REMARK5": "",
            #                 "L42-PRODUCT_REMARK6": "",
            #                 "L43-PRODUCT_REMARK7": "",
            #                 "L44-PRODUCT_REMARK8": "",
            #                 "L45-PRODUCT_REMARK9": "",
            #                 "L46-PRODUCT_REMARK10": ""
            #             }
            #         ],
            #         "F01-LINE_TOTAL_COUNT": "0",
            #         "F02-DELIVERY_OCCUR_DTM": "",
            #         "F03-INVOICE_CURRENCY_CODE": "THB",
            #         "F04-TAX_TYPE_CODE1": "VAT",
            #         "F05-TAX_CAL_RATE1": "7.00",
            #         "F06-BASIS_AMOUNT1": "0.00",
            #         "F07-BASIS_CURRENCY_CODE1": "THB",
            #         "F08-TAX_CAL_AMOUNT1": "43.75",
            #         "F09-TAX_CAL_CURRENCY_CODE1": "THB",
            #         "F10-TAX_TYPE_CODE2": "",
            #         "F11-TAX_CAL_RATE2": "",
            #         "F12-BASIS_AMOUNT2": "",
            #         "F13-BASIS_CURRENCY_CODE2": "",
            #         "F14-TAX_CAL_AMOUNT2": "",
            #         "F15-TAX_CAL_CURRENCY_CODE2": "",
            #         "F16-TAX_TYPE_CODE3": "",
            #         "F17-TAX_CAL_RATE3": "",
            #         "F18-BASIS_AMOUNT3": "",
            #         "F19-BASIS_CURRENCY_CODE3": "",
            #         "F20-TAX_CAL_AMOUNT3": "",
            #         "F21-TAX_CAL_CURRENCY_CODE3": "",
            #         "F22-TAX_TYPE_CODE4": "",
            #         "F23-TAX_CAL_RATE4": "",
            #         "F24-BASIS_AMOUNT4": "",
            #         "F25-BASIS_CURRENCY_CODE4": "",
            #         "F26-TAX_CAL_AMOUNT4": "",
            #         "F27-TAX_CAL_CURRENCY_CODE4": "",
            #         "F28-ALLOWANCE_CHARGE_IND": "false",
            #         "F29-ALLOWANCE_ACTUAL_AMOUNT": "0.00",
            #         "F30-ALLOWANCE_ACTUAL_CURRENCY_CODE": "THB",
            #         "F31-ALLOWANCE_REASON_CODE": "",
            #         "F32-ALLOWANCE_REASON": "",
            #         "F33-PAYMENT_TYPE_CODE": "",
            #         "F34-PAYMENT_DESCRIPTION": "",
            #         "F35-PAYMENT_DUE_DTM": "2025-02-21T00:00:00",
            #         "F36-ORIGINAL_TOTAL_AMOUNT": "0.00",
            #         "F37-ORIGINAL_TOTAL_CURRENCY_CODE": "THB",
            #         "F38-LINE_TOTAL_AMOUNT": "625.00",
            #         "F39-LINE_TOTAL_CURRENCY_CODE": "THB",
            #         "F40-ADJUSTED_INFORMATION_AMOUNT": "0.00",
            #         "F41-ADJUSTED_INFORMATION_CURRENCY_CODE": "THB",
            #         "F42-ALLOWANCE_TOTAL_AMOUNT": "0.00",
            #         "F43-ALLOWANCE_TOTAL_CURRENCY_CODE": "THB",
            #         "F44-CHARGE_TOTAL_AMOUNT": "0.00",
            #         "F45-CHARGE_TOTAL_CURRENCY_CODE": "",
            #         "F46-TAX_BASIS_TOTAL_AMOUNT": "625.00",
            #         "F47-TAX_BASIS_TOTAL_CURRENCY_CODE": "THB",
            #         "F48-TAX_TOTAL_AMOUNT": "43.75",
            #         "F49-TAX_TOTAL_CURRENCY_CODE": "THB",
            #         "F50-GRAND_TOTAL_AMOUNT": "668.75",
            #         "F51-GRAND_TOTAL_CURRENCY_CODE": "THB",
            #         "F52-TERM_PAYMENT": "30 วัน",
            #         "F53-WITHHOLDINGTAX_TYPE1": "",
            #         "F54-WITHHOLDINGTAX_DESCRIPTION1": "",
            #         "F55-WITHHOLDINGTAX_RATE1": "",
            #         "F56-WITHHOLDINGTAX_BASIS_AMOUNT1": "",
            #         "F57-WITHHOLDINGTAX_TAX_AMOUNT1": "",
            #         "F58-WITHHOLDINGTAX_TYPE2": "",
            #         "F59-WITHHOLDINGTAX_DESCRIPTION2": "",
            #         "F60-WITHHOLDINGTAX_RATE2": "",
            #         "F61-WITHHOLDINGTAX_BASIS_AMOUNT2": "",
            #         "F62-WITHHOLDINGTAX_TAX_AMOUNT2": "",
            #         "F63-WITHHOLDINGTAX_TYPE3": "",
            #         "F64-WITHHOLDINGTAX_DESCRIPTION3": "",
            #         "F65-WITHHOLDINGTAX_RATE3": "",
            #         "F66-WITHHOLDINGTAX_BASIS_AMOUNT3": "",
            #         "F67-WITHHOLDINGTAX_TAX_AMOUNT3": "",
            #         "F68-WITHHOLDINGTAX_TOTAL_AMOUNT": "0.00",
            #         "F69-ACTUAL_PAYMENT_TOTAL_AMOUNT": "0.00",
            #         "F70-DOCUMENT_REMARK1": "0.00",
            #         "F71-DOCUMENT_REMARK2": "625.00",
            #         "F72-DOCUMENT_REMARK3": "0.00",
            #         "F73-DOCUMENT_REMARK4": "",
            #         "F74-DOCUMENT_REMARK5": "",
            #         "F75-DOCUMENT_REMARK6": "",
            #         "F76-DOCUMENT_REMARK7": "",
            #         "F77-DOCUMENT_REMARK8": "",
            #         "F78-DOCUMENT_REMARK9": "",
            #         "F79-DOCUMENT_REMARK10": "",
            #         "T01-TOTAL_DOCUMENT_COUNT": "1"
            #     },
            #     "PDFContent": ""
            # }

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
                            'title': 'ข้อผิดพลาด!',
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
                        'title': 'ข้อผิดพลาด!',
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
                    'title': 'ข้อผิดพลาด!',
                    'message': f'เกิดข้อผิดพลาด: {str(etax_data)}',
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

    @api.depends('amount_untaxed', 'original_amount')
    def _compute_difference_amount(self):
        for record in self:
            record.difference_amount = abs((record.original_amount or 0.0) - (record.amount_untaxed or 0.0))

    def _compute_amount_untaxed(self):
        for record in self:
            record.amount_untaxed = sum(line.price_subtotal for line in record.line_ids)
    
    def _compute_amount_cur(self):
        for record in self:
            record.amount_cur = sum(line.price_subtotal for line in record.line_ids)

    def _compute_amount_tax(self):
        for record in self:
            record.amount_tax = (record.amount_untaxed or 0.0) * 0.07
    
    def _compute_net_amount_tax(self):
        for record in self:
            record.amount_vat = (record.net_amount or 0.0) * 0.07

    def _compute_amount_total(self):
        for record in self:
            record.amount_total = (record.difference_amount or 0.0) + (record.amount_tax or 0.0)

    def _compute_net_amount_total(self):
        for record in self:
            record.net_amount_total = (record.total_after_deposit or 0.0) + (record.amount_vat or 0.0)

    def _compute_original_amount(self):
        for record in self:
            record.original_amount = record.invoice_id.amount_total if record.invoice_id else 0.0

    def _compute_amount_disc(self):
        for record in self:
            total_disc = 0.0
            for line in record.line_ids:
                # discount เป็นเปอร์เซ็นต์ เช่น 10 หมายถึง 10%
                line_disc = (line.price_unit * line.quantity) * (line.discount / 100.0)
                total_disc += line_disc
            record.amount_disc = total_disc

    def _compute_net_amount(self):
        for record in self:
            record.net_amount = record.amount_untaxed - (record.amount_disc or 0.0)
            # ผลลัพธ์คือ มูลค่าที่ถูกต้อง (amount_untaxed) - ส่วนลด (amount_disc)

    def _compute_total_after_deposit(self):
        for record in self:
            record.total_after_deposit = (record.net_amount or 0.0) - (record.deposit or 0.0)

    def _compute_invoice_total(self):
        for record in self:
            if record.document_type in ['81', '80']:
                record.invoice_total = record.amount_total
            elif record.document_type in ['380', 'T04']:
                record.invoice_total = record.net_amount_total
            else:
                record.invoice_total = 0.0

class EtaxTransactionLine(models.Model):
    _name = 'etax.transaction.line'
    _description = 'รายการสินค้า E-Tax'

    transaction_id = fields.Many2one('etax.transaction', 'ธุรกรรม', required=True, ondelete='cascade')
    sequence = fields.Integer('ลำดับ', default=10)
    
    product_id = fields.Many2one('product.product', 'สินค้า')
    name = fields.Char('รายละเอียด', related='product_id.name', readonly=True)

    quantity = fields.Float('จำนวน', default=1.0)
    discount = fields.Float('ส่วนลด (%)', default=0.0)
    uom_id = fields.Many2one('uom.uom', 'หน่วย')
    product_name = fields.Char('ชื่อสินค้า', related='product_id.name', readonly=True)
    price_unit = fields.Float('ราคาต่อหน่วย')
    price_subtotal = fields.Float('ราคารวม', compute='_compute_price_subtotal')
    
    tax_ids = fields.Many2many('account.tax', 'etax_line_tax_rel', 'line_id', 'tax_id', 'ภาษี')
    
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit

