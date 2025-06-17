# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class FSMOrderType(models.Model):
    _name = "fsm.order.type"
    _description = "Field Service Order Type"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="ชื่อประเภทงาน", required=True, tracking=True)
    service_date = fields.Date(string="วันที่เข้าบริการ")
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

    