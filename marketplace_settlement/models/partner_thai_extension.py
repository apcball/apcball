from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Thai Localization fields for partners
    default_thai_income_tax_form = fields.Selection([
        ('pnd1', 'PND1'),
        ('pnd2', 'PND2'),
        ('pnd3', 'PND3'),
        ('pnd3a', 'PND3a'),
        ('pnd53', 'PND53'),
    ], string='Default Income Tax Form', 
       help='Default Thai income tax form for this partner')
    
    default_thai_wht_income_type = fields.Selection([
        ('1', '1. เงินเดือน ค่าจ้าง ฯลฯ 40(1)'),
        ('2', '2. ค่าธรรมเนียม ค่านายหน้า ฯลฯ 40(2)'),
        ('3', '3. ค่าแห่งลิขสิทธิ์ ฯลฯ 40(3)'),
        ('4A', '4. ดอกเบี้ย ฯลฯ 40(4)ก'),
    ], string='Default WHT Income Type', 
       help='Default Thai WHT income type for this partner')
    
    is_thai_wht_enabled = fields.Boolean(
        string='Enable Thai WHT',
        default=False,
        help='Enable Thai withholding tax features for this partner'
    )
