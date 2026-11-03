# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    buz_asset_auto_post = fields.Boolean(
        string='ลงบัญชีค่าเสื่อมราคาอัตโนมัติ', default=False,
        help="ปิดไว้เป็นค่าเริ่มต้น: ระบบจะไม่ลงบัญชีเองจนกว่าฝ่ายบัญชีจะเปิดใช้")
