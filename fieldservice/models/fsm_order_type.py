# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class FSMOrderType(models.Model):
    _name = "fsm.order.type"
    _description = "Field Service Order Type"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Document Number', required=True, readonly=True, copy=False, default='New')
    date_notice = fields.Date(string='Date Notified')
    warranty_number = fields.Char(string='Warranty Number')
    date_service = fields.Date(string='Date of Service')
    informant_name = fields.Char(string='Informant')
    informant_mobile = fields.Char(string='Mobile')
    requester_name = fields.Char(string='Requester')
    requester_phone = fields.Char(string='Phone')
    shop_name = fields.Char(string='Shop Name')
    appointment_info = fields.Char(string='Appointment Info')
    address = fields.Text(string='Address')
    mobile = fields.Char(string="Mobile")

    date_service = fields.Datetime(string='วันที่เข้ารับบริการ')
    planned_date = fields.Date(string="Planned Date")    # ตัวอย่างชื่อที่ต่างกัน
    scheduled_date = fields.Datetime(string="Scheduled Date")
    internal_type = fields.Selection(
        selection=[("fsm", "FSM")],
        default="fsm",
        string="ประเภทระบบภายใน",
        tracking=True,
    )


class FSMOrder(models.Model):
    _inherit = "fsm.order"

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="ชื่อผู้ขอรับบริการ (ลูกค้า)",
        tracking=True,
    )
    reported_by_id = fields.Many2one(
        comodel_name='res.partner',
        string="ผู้แจ้ง",
    )
    date_notice = fields.Date(string="วันที่แจ้ง")
    store_name = fields.Char(string="ซื้อผ่านร้าน")
    missing_appointment_note = fields.Text(string="ข้อมูลนัดหาย")
    warranty_number = fields.Char(string="เลขที่ใบรับประกัน")
    order_type_id = fields.Many2one(
        comodel_name='fsm.order.type',
        string="ประเภทงาน",
    )

    