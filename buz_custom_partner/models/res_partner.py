# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    partner_code = fields.Char(
        string='Partner Code',
        readonly=True,
        copy=False,
        index=True,
        help="Auto-generated code: Customer -> Cxxxxx, Vendor -> Vxxxxx."
    )
    old_code_partner = fields.Char(string='Old Code Partner')
    office = fields.Char(string='Office')
    partner_group = fields.Char(string='Partner Group')
    partner_type = fields.Char(string='Partner Type')

    _sql_constraints = [
        ('partner_code_uniq', 'unique(partner_code)', 'Partner Code must be unique!')
    ]

    # --- Utilities -----------------------------------------------------------
    def _get_target_sequence_code(self, vals=None):
        """
        ตัดสินใจว่าจะใช้ซีเควนซ์ฝั่งไหน
        ลำดับความสำคัญ:
            1) ถ้าเป็น Vendor (supplier_rank > 0) -> vendor
            2) ถ้าเป็น Customer (customer_rank > 0) -> customer
        ดูจาก vals ที่ถูกส่งมาตอน create/write ก่อน ถ้าไม่มีค่อย fallback มาที่ค่าบน record
        """
        self.ensure_one()
        vals = vals or {}
        supplier_rank = vals.get('supplier_rank', self.supplier_rank)
        customer_rank = vals.get('customer_rank', self.customer_rank)

        # เผื่อกรณีบางฟอร์มหรือ context เซ็ต default_* มาให้
        if supplier_rank or self.env.context.get('default_supplier_rank'):
            return 'custom_partner_code.vendor'
        if customer_rank or self.env.context.get('default_customer_rank'):
            return 'custom_partner_code.customer'
        return False

    def _assign_partner_code_if_needed(self, vals=None):
        """กำหนด partner_code ถ้ายังไม่มี และพอจะระบุประเภทได้"""
        for partner in self:
            if not partner.partner_code:
                seq_code = partner._get_target_sequence_code(vals=vals or {})
                if seq_code:
                    partner.partner_code = self.env['ir.sequence'].next_by_code(seq_code)

    # --- Overrides -----------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        # จ่าย code หลังจากสร้าง (ปลอดภัยต่อ name_get/constraint อื่น)
        for partner, vals in zip(partners, vals_list):
            partner._assign_partner_code_if_needed(vals=vals)
        return partners

    def write(self, vals):
        res = super().write(vals)
        # ถ้าเพิ่งเปลี่ยนให้กลายเป็น customer/vendor ทีหลัง ให้เติม code ให้เลยถ้ายังไม่มี
        self._assign_partner_code_if_needed(vals=vals)
        return res
