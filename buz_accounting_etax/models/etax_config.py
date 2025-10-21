from odoo import models, fields, api
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class EtaxConfig(models.Model):
    _name = 'etax.config'
    _description = 'การตั้งค่า E-Tax API'
    _rec_name = 'name'

    name = fields.Char('ชื่อการตั้งค่า', required=True)
    active = fields.Boolean('ใช้งาน', default=True)
    
    # ข้อมูลการเชื่อมต่อ API
    api_url = fields.Char('URL API', required=True, 
                         default='https://uatservice-etax.one.th/service/etaxsigndocumentjson')
    seller_tax_id = fields.Char('เลขประจำตัวผู้เสียภาษี', required=True, size=13)
    seller_branch_id = fields.Char('รหัสสาขา', required=True, default='00000')
    api_key = fields.Text('API Key', required=True)
    user_code = fields.Char('รหัสผู้ใช้', required=True)
    access_key = fields.Char('รหัสการเข้าถึง', required=True)
    service_code = fields.Char('รหัสบริการ', required=True, default='S03')
    
    # ข้อมูลบริษัท
    company_id = fields.Many2one('res.company', 'บริษัท', required=True, 
                                default=lambda self: self.env.company)
    
    # การตั้งค่า PDF
    pdf_template_id = fields.Char('Template PDF', default='smm_T04')
    send_mail_ind = fields.Selection([
        ('Y', 'ส่งอีเมล'),
        ('N', 'ไม่ส่งอีเมล')
    ], 'ส่งอีเมลอัตโนมัติ', default='Y')
    
    def test_connection(self):
        """ทดสอบการเชื่อมต่อ API"""
        try:
            # สร้างข้อมูลทดสอบ
            test_data = {
                "SellerTaxId": self.seller_tax_id,
                "SellerBranchId": self.seller_branch_id,
                "APIKey": self.api_key,
                "UserCode": self.user_code,
                "AccessKey": self.access_key,
                "ServiceCode": self.service_code,
                "TextContent": {
                    "C01-SELLER_TAX_ID": self.seller_tax_id,
                    "H03-DOCUMENT_ID": "TEST001",
                },
                "PDFContent": ""
            }
            
            headers = {
                'Content-Type': 'application/json',
            }
            
            response = requests.post(self.api_url, 
                                   data=json.dumps(test_data), 
                                   headers=headers, 
                                   timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'OK':
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'สำเร็จ!',
                            'message': 'การเชื่อมต่อ E-Tax API สำเร็จ',
                            'type': 'success',
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'ข้อผิดพลาด!',
                            'message': f'API ตอบกลับ: {result.get("message", "ไม่ทราบสาเหตุ")}',
                            'type': 'warning',
                        }
                    }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'ข้อผิดพลาด!',
                        'message': f'HTTP Error: {response.status_code}',
                        'type': 'danger',
                    }
                }
                
        except Exception as e:
            _logger.error(f"E-Tax API Test Error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'ข้อผิดพลาด!',
                    'message': f'เกิดข้อผิดพลาด: {str(e)}',
                    'type': 'danger',
                }
            }