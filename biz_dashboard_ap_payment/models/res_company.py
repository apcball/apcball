# -*- coding: utf-8 -*-
from odoo import fields, models

from .ap_dashboard import clear_cache


class ResCompany(models.Model):
    _inherit = 'res.company'

    apd_other_expense_account_ids = fields.Many2many(
        'account.account', 'apd_company_other_expense_account_rel',
        'company_id', 'account_id',
        string='บัญชีรายจ่ายนอกบิล (Payment Dashboard)',
        domain="[('company_id', '=', id)]",
        help='บัญชีที่รายการสมุดรายวัน (ไม่ผ่านบิลเจ้าหนี้) ถูกนับรวมในยอดจ่ายประจำเดือน '
             'เช่น เงินเดือน ดอกเบี้ย')

    apd_other_expense_debit_account_ids = fields.Many2many(
        'account.account', 'apd_company_other_expense_debit_account_rel',
        'company_id', 'account_id',
        string='บัญชีรายจ่ายนอกบิล - ด้านเดบิตเท่านั้น (Payment Dashboard)',
        domain="[('company_id', '=', id)]",
        help='บัญชีที่นับเฉพาะรายการด้านเดบิตของสมุดรายวัน (ไม่ผ่านบิลเจ้าหนี้) เช่น ชำระคืนเงินกู้ '
             'เงินประกันสังคม เงินเดือน ค่าแรง ดอกเบี้ยจ่าย ส่วนบัญชีใน "บัญชีรายจ่ายนอกบิล" '
             'นับเดบิตหักเครดิต (ค่าใช้จ่ายค้างจ่าย)')

    apd_loan_account_ids = fields.Many2many(
        'account.account', 'apd_company_loan_account_rel',
        'company_id', 'account_id',
        string='บัญชีเงินกู้ธนาคาร (Payment Dashboard)',
        domain="[('company_id', '=', id)]",
        help='บัญชีเงินกู้ยืมระยะสั้นที่ใช้จ่ายเจ้าหนี้ เช่น TR / PN — การจ่ายบิลที่ลงเครดิตบัญชีเหล่านี้ '
             'จะแยกเป็น "ด้วยเงินกู้" ในยอดจ่ายจริง และแสดงยอดคงค้างสินเชื่อ')

    apd_note_journal_ids = fields.Many2many(
        'account.journal', 'apd_company_note_journal_rel',
        'company_id', 'journal_id',
        string='สมุดรายวันตั๋วเงินจ่าย (Payment Dashboard)',
        domain="[('company_id', '=', id)]",
        help='การชำระผ่านสมุดรายวันเหล่านี้ถือเป็น "ด้วยตั๋วเงินจ่าย" (เงินยังไม่ออกจนตั๋วครบกำหนด)')
    apd_advance_journal_ids = fields.Many2many(
        'account.journal', 'apd_company_advance_journal_rel',
        'company_id', 'journal_id',
        string='สมุดรายวันเงินทดรองจ่าย (Payment Dashboard)',
        domain="[('company_id', '=', id)]",
        help='การชำระผ่านสมุดรายวันเหล่านี้ถือเป็น "ด้วยเงินทดรองจ่าย" (พนักงานสำรองจ่าย บริษัทยังต้องคืน)')

    def write(self, vals):
        res = super().write(vals)
        if {'apd_other_expense_account_ids', 'apd_other_expense_debit_account_ids', 'apd_loan_account_ids',
                'apd_note_journal_ids', 'apd_advance_journal_ids'} & set(vals):
            clear_cache()
        return res
