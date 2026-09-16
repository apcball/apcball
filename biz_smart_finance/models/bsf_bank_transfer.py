# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BsfBankTransfer(models.Model):
    """แผนโอนเงินระหว่างธนาคาร (บริษัทเดียวกัน) — กรอกมือหรือระบบเสนอให้
    (origin=suggested) จากช่องว่างที่คาดว่าจะหลุด buffer ใน 13 สัปดาห์"""

    _name = "biz.smart.finance.bank.transfer"
    _description = "Smart Finance Interbank Transfer Plan"
    _order = "execution_date, id"

    source_bank_id = fields.Many2one(
        "biz.smart.finance.bank", string="บัญชีต้นทาง", required=True,
    )
    dest_bank_id = fields.Many2one(
        "biz.smart.finance.bank", string="บัญชีปลายทาง", required=True,
    )
    company_id = fields.Many2one(
        related="source_bank_id.company_id", store=True, readonly=True, index=True,
    )
    currency_id = fields.Many2one(
        related="source_bank_id.currency_id", store=True, readonly=True,
    )
    amount = fields.Monetary(
        string="จำนวนเงิน", currency_field="currency_id", required=True,
    )
    execution_date = fields.Date(
        string="วันที่ดำเนินการ", required=True, default=fields.Date.context_today,
    )
    purpose = fields.Selection(
        [
            ("liquidity", "Liquidity Support"),
            ("working_capital", "Working Capital"),
            ("cash_pool", "Cash Pool Balancing"),
            ("debt_service", "Debt Service"),
            ("other", "อื่น ๆ"),
        ],
        string="วัตถุประสงค์", required=True, default="liquidity",
    )
    state = fields.Selection(
        [
            ("draft", "รออนุมัติ"),
            ("approved", "อนุมัติแล้ว"),
            ("done", "โอนแล้ว"),
            ("cancel", "ยกเลิก"),
        ],
        string="สถานะอนุมัติ", required=True, default="draft", index=True,
    )
    origin = fields.Selection(
        [("manual", "กรอกมือ"), ("suggested", "ระบบเสนอ")],
        string="ที่มา", required=True, default="manual",
    )
    note = fields.Char(string="หมายเหตุ")

    @api.constrains("source_bank_id", "dest_bank_id")
    def _check_banks(self):
        for rec in self:
            if rec.source_bank_id == rec.dest_bank_id:
                raise ValidationError(
                    _("บัญชีต้นทางและปลายทางต้องไม่ใช่บัญชีเดียวกัน"))
            if rec.source_bank_id.company_id != rec.dest_bank_id.company_id:
                raise ValidationError(
                    _("โอนระหว่างธนาคารต้องอยู่บริษัทเดียวกัน — ถ้าข้ามบริษัท "
                      "คือเงินให้กู้ยืมระหว่างกัน ไม่ใช่ interbank transfer"))

    @api.constrains("amount")
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("จำนวนเงินต้องมากกว่า 0"))

    def action_approve(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "approved"})

    def action_done(self):
        self.filtered(lambda r: r.state == "approved").write({"state": "done"})

    def action_cancel(self):
        self.filtered(lambda r: r.state in ("draft", "approved")).write(
            {"state": "cancel"})

    def action_draft(self):
        self.filtered(lambda r: r.state == "cancel").write({"state": "draft"})
