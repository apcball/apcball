# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class BsfBank(models.Model):
    """ทะเบียนธนาคาร — 1 แถว = 1 บรรทัดในตาราง Bank Balance/Cash Position
    รวมได้หลาย journal ของธนาคารเดียวกัน (เช่นบัญชีออมทรัพย์ + กระแสรายวัน)"""

    _name = "biz.smart.finance.bank"
    _description = "Smart Finance Bank Register"
    _order = "sequence, name"

    name = fields.Char(string="ชื่อธนาคาร", required=True)
    sequence = fields.Integer(string="ลำดับ", default=10)
    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", store=True, readonly=True,
    )
    bank_id = fields.Many2one(
        "res.bank", string="ธนาคาร (res.bank)",
        help="อ้างอิงเฉย ๆ / ใช้ตอนสร้างแถวอัตโนมัติจากสมุดรายวัน",
    )
    journal_ids = fields.One2many(
        "account.journal", "bsf_bank_id", string="สมุดรายวัน",
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    is_restricted = fields.Boolean(
        string="กันไว้ทั้งบัญชี",
        help="เช่นบัญชี escrow/ค้ำประกัน — ยอดทั้งหมดนับเป็น Restricted Cash",
    )
    restricted_amount = fields.Monetary(
        string="เงินสดที่กันไว้บางส่วน", currency_field="currency_id",
        help="ใช้เมื่อไม่ได้กันไว้ทั้งบัญชี — เช่นวงเงินค้ำประกันสัญญาที่กันไว้",
    )
    min_balance = fields.Monetary(
        string="ยอดคงเหลือขั้นต่ำ (Buffer)", currency_field="currency_id",
        help="เส้นเตือนรายธนาคาร — ต่ำกว่านี้ขึ้นสถานะ At Risk",
    )
    receipt_share_pct = fields.Float(
        string="สัดส่วนเงินเข้า (%) — ตั้งทับ",
        help="0 = ให้ระบบคิดจากประวัติการเดินบัญชีย้อนหลังอัตโนมัติ",
    )
    payment_share_pct = fields.Float(
        string="สัดส่วนเงินออก (%) — ตั้งทับ",
        help="0 = ให้ระบบคิดจากประวัติการเดินบัญชีย้อนหลังอัตโนมัติ",
    )
    facility_ids = fields.One2many(
        "biz.smart.finance.bank.facility", "bank_id", string="วงเงินสินเชื่อ",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("bsf_bank_receipt_share_pct_range",
         "check(receipt_share_pct >= 0 and receipt_share_pct <= 100)",
         "สัดส่วนเงินเข้าต้องอยู่ระหว่าง 0-100"),
        ("bsf_bank_payment_share_pct_range",
         "check(payment_share_pct >= 0 and payment_share_pct <= 100)",
         "สัดส่วนเงินออกต้องอยู่ระหว่าง 0-100"),
    ]

    @api.model
    def action_bsf_seed_from_journals(self, company_ids=None):
        """สร้างแถวธนาคารจากสมุดรายวัน bank/cash ที่ยังไม่ได้ผูกธนาคาร —
        ตั้งชื่อจากธนาคารของเลขบัญชี ถ้าไม่มีให้ใช้ชื่อสมุดรายวันแทน
        (bank_account_id และ bank_id เป็น optional ทั้งคู่)"""
        domain = [("type", "in", ("bank", "cash")), ("bsf_bank_id", "=", False)]
        if company_ids:
            domain.append(("company_id", "in", company_ids))
        journals = self.env["account.journal"].search(domain)
        created = self.browse()
        for journal in journals:
            bank = journal.bank_account_id.bank_id
            vals = {
                "name": bank.name or journal.name,
                "company_id": journal.company_id.id,
                "bank_id": bank.id or False,
            }
            row = self.create(vals)
            journal.bsf_bank_id = row.id
            created |= row
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("สร้างทะเบียนธนาคาร"),
                "message": _("สร้าง %s รายการจากสมุดรายวัน") % len(created),
                "type": "success" if created else "warning",
            },
        }
