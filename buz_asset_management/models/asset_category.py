# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BuzAssetCategory(models.Model):
    _name = 'buz.asset.category'
    _description = 'หมวดหมู่ทรัพย์สิน'
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(required=True, string='ชื่อ')
    code = fields.Char(string='รหัส')
    active = fields.Boolean(default=True, string='เปิดใช้งาน')
    # Empty company = global category (usable by every company).
    company_id = fields.Many2one('res.company', index=True, default=lambda self: self.env.company, string='บริษัท')
    tracking_mode = fields.Selection([
        ('individual', 'รายตัว'),
        ('grouped', 'แบบกลุ่ม'),
    ], required=True, default='individual', string='รูปแบบการติดตาม')

    # Depreciation defaults. Accounting depreciation only; straight-line MVP.
    depreciation_method = fields.Selection(
        [('straight_line', 'เส้นตรง')], required=True, default='straight_line', string='วิธีคิดค่าเสื่อมราคา')
    depreciation_frequency = fields.Selection(
        [('monthly', 'รายเดือน')], required=True, default='monthly', string='ความถี่การตัดค่าเสื่อมราคา')
    useful_life_months = fields.Integer(string='อายุการใช้งาน (เดือน)')

    # Accounts are company-specific: never hardcode account codes.
    asset_account_id = fields.Many2one(
        'account.account', string='บัญชีสินทรัพย์ถาวร', check_company=True)
    depreciation_account_id = fields.Many2one(
        'account.account', string='บัญชีค่าเสื่อมราคาสะสม', check_company=True)
    expense_account_id = fields.Many2one(
        'account.account', string='บัญชีค่าใช้จ่ายค่าเสื่อมราคา', check_company=True)
    gain_loss_account_id = fields.Many2one(
        'account.account', string='บัญชีกำไร/ขาดทุนจากการจำหน่าย', check_company=True)
    disposal_clearing_account_id = fields.Many2one(
        'account.account', string='บัญชีพักการจำหน่าย', check_company=True)
    journal_id = fields.Many2one(
        'account.journal', string='สมุดรายวันค่าเสื่อมราคา', check_company=True)

    require_department = fields.Boolean(string='ต้องระบุแผนก')
    require_qr = fields.Boolean(string='ต้องมีป้าย QR')

    _sql_constraints = [
        ('useful_life_non_negative', 'CHECK(useful_life_months >= 0)',
         'อายุการใช้งานต้องไม่ติดลบ'),
    ]

    @api.constrains('company_id', 'asset_account_id', 'depreciation_account_id',
                    'expense_account_id', 'gain_loss_account_id',
                    'disposal_clearing_account_id', 'journal_id')
    def _check_accounting_company(self):
        # Global categories cannot carry company-specific accounts.
        for category in self.filtered(lambda c: not c.company_id):
            linked = (category.asset_account_id | category.depreciation_account_id
                      | category.expense_account_id | category.gain_loss_account_id
                      | category.disposal_clearing_account_id)
            if linked or category.journal_id:
                raise ValidationError(_(
                    "หมวดหมู่ '%s' ไม่ได้ระบุบริษัท จึงกำหนดบัญชีหรือสมุดรายวันไม่ได้ กรุณาระบุบริษัทก่อน", category.name))
