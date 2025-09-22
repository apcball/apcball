# -*- coding: utf-8 -*-
from odoo import api, fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    wht_payable_account_id = fields.Many2one(
        "account.account",
        string="WHT Payable Account (TH)",
        domain="[('account_type', '=', 'liability_current')]",
        help="บัญชีภาษีหัก ณ ที่จ่าย (เจ้าหนี้กรมสรรพากร) สำหรับผู้จ่ายเงิน",
    config_parameter="account_wht_installment.wht_payable_account_id",
    default_model='res.company',
    )
    default_wht_percent = fields.Float(
        string="Default WHT %",
        default=3.0,
        help="อัตราภาษีหัก ณ ที่จ่ายเริ่มต้น (ปรับได้ในวิซาร์ด)",
    config_parameter="account_wht_installment.default_wht_percent",
    default_model='res.company',
    )
    bank_charge_account_id = fields.Many2one(
        "account.account",
        string="Bank Charge Account",
        domain="[('account_type', '=', 'expense')]",
        help="บัญชีค่าธรรมเนียมธนาคาร สำหรับบันทึกค่าใช้จ่ายในการโอนเงิน",
        config_parameter="account_wht_installment.bank_charge_account_id",
        default_model='res.company',
    )
    
    # VAT handling for partial payments
    enable_vat_on_partial_payment = fields.Boolean(
        string="Enable VAT calculation on partial payments",
        default=True,
        help="เปิดใช้งานการคำนวณ VAT สำหรับการจ่ายเงินบางส่วน",
        config_parameter="account_wht_installment.enable_vat_on_partial_payment",
        default_model='res.company',
    )
