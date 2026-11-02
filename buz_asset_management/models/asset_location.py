# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BuzAssetLocation(models.Model):
    _name = 'buz.asset.location'
    _description = 'สถานที่ตั้งทรัพย์สิน'
    _order = 'complete_name'
    _rec_name = 'complete_name'
    _check_company_auto = True

    name = fields.Char(required=True, string='ชื่อ')
    code = fields.Char(string='รหัส')
    complete_name = fields.Char(compute='_compute_complete_name', store=True, string='ชื่อเต็ม')
    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company, string='บริษัท')
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='คลังสินค้า', index=True, check_company=True)
    # Picked from the stock locations of the system; narrowed to the warehouse when set.
    parent_id = fields.Many2one(
        'stock.location', string='สถานที่ตั้งหลัก', index=True, ondelete='restrict',
        check_company=True,
        domain="[('usage', '=', 'internal'), ('warehouse_id', '=?', warehouse_id)]")
    location_type = fields.Selection([
        ('site', 'พื้นที่'),
        ('building', 'อาคาร'),
        ('floor', 'ชั้น'),
        ('room', 'ห้อง'),
        ('storage', 'ที่จัดเก็บ'),
        ('other', 'อื่นๆ'),
    ], string='ประเภท')
    address = fields.Text(string='ที่อยู่')
    active = fields.Boolean(default=True, string='เปิดใช้งาน')

    _sql_constraints = [
        ('code_company_uniq', 'unique(company_id, code)',
         'รหัสสถานที่ตั้งต้องไม่ซ้ำกันภายในบริษัท'),
    ]

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for location in self:
            if location.parent_id:
                location.complete_name = '%s / %s' % (
                    location.parent_id.complete_name, location.name)
            else:
                location.complete_name = location.name

    @api.onchange('warehouse_id')
    def _onchange_warehouse_id(self):
        if self.warehouse_id and self.parent_id.warehouse_id != self.warehouse_id:
            self.parent_id = False

    @api.constrains('warehouse_id', 'parent_id')
    def _check_parent_warehouse(self):
        for location in self:
            parent_warehouse = location.parent_id.warehouse_id
            if location.warehouse_id and parent_warehouse and location.warehouse_id != parent_warehouse:
                raise ValidationError(_(
                    "สถานที่ตั้งหลักอยู่ในคลัง %(parent)s ไม่ใช่ %(warehouse)s",
                    parent=parent_warehouse.display_name,
                    warehouse=location.warehouse_id.display_name))
