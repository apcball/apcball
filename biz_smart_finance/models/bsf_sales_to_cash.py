# -*- coding: utf-8 -*-
"""Sales-to-Cash planning data.  These records are planning only; they never
create deliveries, invoices, payments, or accounting entries."""
import calendar
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    bsf_cash_source = fields.Selection([
        ("sales_to_cash", "Sales to Cash"),
        ("project_plan", "แผนรับเงินโครงการ"),
    ], string="แหล่งประมาณการเงินรับ", default="sales_to_cash", required=True)
    bsf_delivery_plan_ids = fields.One2many(
        "biz.smart.finance.delivery.plan", "sale_order_id", string="แผนส่งมอบ Sales to Cash")

    @api.constrains("bsf_delivery_plan_ids", "order_line")
    def _check_bsf_delivery_plan_quantity(self):
        for order in self:
            planned = {}
            for plan in order.bsf_delivery_plan_ids:
                planned[plan.sale_line_id] = planned.get(plan.sale_line_id, 0.0) + plan.quantity
            for line, quantity in planned.items():
                if quantity > line.product_uom_qty + 1e-6:
                    raise ValidationError(_("จำนวนในแผนส่งมอบเกินจำนวนสั่งขายของ %s") % line.display_name)


class BsfDeliveryPlan(models.Model):
    _name = "biz.smart.finance.delivery.plan"
    _description = "Sales to Cash Delivery Plan"
    _order = "delivery_date, id"

    sale_order_id = fields.Many2one("sale.order", required=True, ondelete="cascade", index=True)
    sale_line_id = fields.Many2one("sale.order.line", required=True, ondelete="cascade", index=True,
        domain="[('order_id', '=', sale_order_id), ('display_type', '=', False)]")
    company_id = fields.Many2one(related="sale_order_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="sale_order_id.currency_id", store=True)
    delivery_date = fields.Date(string="วันส่งมอบ", required=True, index=True)
    quantity = fields.Float(string="จำนวนส่ง", required=True)
    amount = fields.Monetary(string="ยอดเงินรวม", currency_field="currency_id", compute="_compute_amount", store=True)

    @api.depends("quantity", "sale_line_id.price_total", "sale_line_id.product_uom_qty")
    def _compute_amount(self):
        for rec in self:
            total_qty = rec.sale_line_id.product_uom_qty or 0.0
            rec.amount = rec.sale_line_id.price_total * rec.quantity / total_qty if total_qty else 0.0

    @api.constrains("quantity")
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("จำนวนส่งต้องมากกว่า 0"))
            planned = sum(rec.sale_order_id.bsf_delivery_plan_ids.filtered(
                lambda plan: plan.sale_line_id == rec.sale_line_id).mapped("quantity"))
            if planned > rec.sale_line_id.product_uom_qty + 1e-6:
                raise ValidationError(_("จำนวนในแผนส่งมอบเกินจำนวนสั่งขายของ %s") % rec.sale_line_id.display_name)


class BsfCollectionFollowup(models.Model):
    _name = "biz.smart.finance.collection.followup"
    _description = "Sales to Cash Collection Follow-up"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "next_action_date, id"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    move_line_id = fields.Many2one("account.move.line", string="ลูกหนี้", ondelete="cascade", index=True)
    external_invoice_id = fields.Many2one("biz.smart.finance.ext.invoice", string="ลูกหนี้ภายนอก", ondelete="cascade")
    partner_id = fields.Many2one("res.partner", required=True, index=True)
    owner_id = fields.Many2one("res.users", string="ผู้รับผิดชอบ", required=True, default=lambda self: self.env.user)
    promised_date = fields.Date(string="วันนัดรับเงิน", index=True)
    promised_amount = fields.Monetary(string="ยอดนัดรับ", currency_field="currency_id")
    next_action_date = fields.Date(string="วันติดตามครั้งถัดไป", index=True)
    dispute = fields.Boolean(string="มีข้อพิพาท")
    reason = fields.Selection([("cash", "ลูกค้ารอเงิน"), ("document", "เอกสารไม่ครบ"), ("dispute", "ข้อพิพาท"), ("other", "อื่น ๆ")], string="เหตุผล")
    note = fields.Text(string="บันทึกการติดตาม")
    state = fields.Selection([("open", "ติดตาม"), ("done", "เสร็จสิ้น"), ("cancel", "ยกเลิก")], default="open", required=True, tracking=True)

    def action_done(self):
        self.write({"state": "done"})
