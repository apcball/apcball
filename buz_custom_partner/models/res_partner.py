# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    _rec_names_search = [
        'complete_name', 'email', 'ref', 'vat', 'company_registry', 'partner_code',
    ]

    partner_code = fields.Char(
        string='Partner Code',
        readonly=True,
        copy=False,
        index=True,
        help="Auto-generated code: Customer -> Cxxxxx, Vendor -> Vxxxxx."
    )
    old_code_partner = fields.Char(string='Old Code Partner')
    is_construction_vendor = fields.Boolean(
        string='Is Construction Vendor',
        copy=False,
        help="Construction subcontractor/vendor. Marks the partner as a vendor "
             "and assigns a K-series partner code (Kxxxxx) when it has no code yet.",
    )
    office = fields.Char(string='Office')
    partner_group_id = fields.Many2one(
        'buz.partner.group',
        string='Partner Group',
        ondelete='restrict',
        index=True,
        help="Select a predefined partner group (managed under Contacts > Configuration).",
    )
    partner_type_id = fields.Many2one(
        'buz.partner.type',
        string='Partner Type',
        ondelete='restrict',
        index=True,
        help="Select a predefined partner type (managed under Contacts > Configuration).",
    )
    buz_partner_kind = fields.Selection(
        [('customer', 'Customer'), ('vendor', 'Vendor')],
        string='Partner Kind',
        compute='_compute_buz_partner_kind',
        help="Technical: used to filter Partner Group / Type lists per customer or vendor.",
    )

    @api.depends('supplier_rank', 'customer_rank')
    def _compute_buz_partner_kind(self):
        for partner in self:
            partner.buz_partner_kind = 'vendor' if partner.supplier_rank else 'customer'

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
        is_construction_vendor = vals.get(
            'is_construction_vendor', self.is_construction_vendor)
        is_vendor = supplier_rank or self.env.context.get('default_supplier_rank')

        # เผื่อกรณีบางฟอร์มหรือ context เซ็ต default_* มาให้
        if is_construction_vendor and is_vendor:
            return 'custom_partner_code.construction_vendor'
        if is_vendor:
            return 'custom_partner_code.vendor'
        if customer_rank or self.env.context.get('default_customer_rank'):
            return 'custom_partner_code.customer'
        return False

    @api.model
    def _force_supplier_rank_for_construction(self, vals, record=None):
        """ติ๊ก is_construction_vendor -> บังคับให้เป็น vendor (supplier_rank >= 1)"""
        is_cv = vals.get(
            'is_construction_vendor',
            record.is_construction_vendor if record else False,
        )
        if not is_cv:
            return vals
        current_rank = vals.get(
            'supplier_rank',
            record.supplier_rank if record else 0,
        )
        if not current_rank:
            vals = dict(vals, supplier_rank=1)
        return vals

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
        vals_list = [
            self._force_supplier_rank_for_construction(vals or {})
            for vals in vals_list
        ]
        partners = super().create(vals_list)
        # จ่าย code หลังจากสร้าง (ปลอดภัยต่อ name_get/constraint อื่น)
        for partner, vals in zip(partners, vals_list):
            partner._assign_partner_code_if_needed(vals=vals)
        return partners

    def write(self, vals):
        if vals.get('is_construction_vendor') and 'supplier_rank' not in vals:
            vals = dict(vals, supplier_rank=1)
        res = super().write(vals)
        # ถ้าเพิ่งเปลี่ยนให้กลายเป็น customer/vendor ทีหลัง ให้เติม code ให้เลยถ้ายังไม่มี
        self._assign_partner_code_if_needed(vals=vals)
        return res
