# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

# ประเภทบัญชี — ชุดเดียวกับ account.account.account_type ของ core เป๊ะ ๆ
# (ห้ามเพิ่ม/ลด) เพราะ engine ใช้ค่านี้เข้า BS_WATERFALL / PNL_WATERFALL /
# CF_*_TYPES ตัวเดียวกับบัญชี Odoo — ผังภายนอกจึงไหลเข้างบได้โดยไม่ต้องแก้ engine
ACCOUNT_TYPES = [
    ("asset_receivable", "ลูกหนี้การค้า"),
    ("asset_cash", "เงินสดและรายการเทียบเท่าเงินสด"),
    ("asset_current", "สินทรัพย์หมุนเวียนอื่น"),
    ("asset_prepayments", "ค่าใช้จ่ายจ่ายล่วงหน้า"),
    ("asset_fixed", "ที่ดิน อาคารและอุปกรณ์"),
    ("asset_non_current", "สินทรัพย์ไม่หมุนเวียนอื่น"),
    ("liability_payable", "เจ้าหนี้การค้า"),
    ("liability_credit_card", "บัตรเครดิต"),
    ("liability_current", "หนี้สินหมุนเวียนอื่น"),
    ("liability_non_current", "หนี้สินไม่หมุนเวียน"),
    ("equity", "ทุนและส่วนของผู้ถือหุ้นอื่น"),
    ("equity_unaffected", "กำไรสะสม (ยกมา)"),
    ("income", "รายได้"),
    ("income_other", "รายได้อื่น"),
    ("expense_direct_cost", "ต้นทุนขาย/บริการ"),
    ("expense", "ค่าใช้จ่ายในการดำเนินงาน"),
    ("expense_depreciation", "ค่าเสื่อมราคา/ตัดจำหน่าย"),
    ("off_balance", "นอกงบดุล"),
]
ACCOUNT_TYPE_SET = {k for k, _label in ACCOUNT_TYPES}


class BsfExtAccount(models.Model):
    """ผังบัญชีของระบบเดิม — เก็บรหัส/ชื่อตามระบบนั้นไว้ตรง ๆ แล้ว map แค่
    **ประเภทบัญชี** มาที่ชุดของ Odoo

    จงใจไม่บังคับให้สร้างบัญชีใน `account.account` ให้ครบก่อน เพราะผังของระบบเก่า
    มักไม่ตรงกับผัง Odoo และการยัดเข้าไปจะทำให้ผังจริงเลอะ — engine ใช้คีย์
    **สังเคราะห์ติดลบ** `-(ext_account.id)` แทน account_id จริง ซึ่งเป็นกลไก
    เดียวกับที่ `_build_shared` ใช้กับคู่ค้าภายนอกอยู่แล้ว (`ext_partner_keys`)
    ผลคือ BS_WATERFALL / PNL_WATERFALL / _pl_from_balances / _sum_type /
    _build_compare ทำงานกับบัญชีภายนอกได้โดยไม่ต้องแก้อะไรเลย

    ข้อแลกเปลี่ยน: แถวบัญชีภายนอกในงบ **คลิก drill ลง journal item ไม่ได้**
    (ไม่มีเอกสารต้นทางใน Odoo) — engine ส่ง `drillable: False` มาให้ฝั่งจอ
    """

    _name = "biz.smart.finance.ext.account"
    _description = "Smart Finance External Account (legacy chart)"
    _order = "company_id, code"
    _rec_name = "display_name"

    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
        default=lambda self: self.env.company,
    )
    code = fields.Char(
        string="รหัสบัญชี", required=True, index=True,
        help="รหัสตามผังบัญชีของระบบเดิม — ใช้เป็นกุญแจตอนนำเข้า Trial Balance ซ้ำ",
    )
    name = fields.Char(string="ชื่อบัญชี", required=True)
    account_type = fields.Selection(
        ACCOUNT_TYPES, string="ประเภทบัญชี", required=True, index=True,
        help="ตัวกำหนดว่าบัญชีนี้ไปอยู่บรรทัดไหนของงบดุล/งบกำไรขาดทุน/งบกระแสเงินสด",
    )
    active = fields.Boolean(default=True)

    # ธงแทน M2M ของ config (bsf.config ผูกกับ account.account จึงชี้บัญชี
    # ภายนอกไม่ได้) — _pl_from_balances อ่านสองทางควบคู่กัน
    is_depreciation = fields.Boolean(
        string="เป็นบัญชีค่าเสื่อม/ตัดจำหน่าย",
        help="ใช้บวกกลับตอนคำนวณ EBITDA — ประเภท 'ค่าเสื่อมราคา' ระบบบวกให้อยู่แล้ว "
             "ธงนี้ไว้สำหรับค่าเสื่อมที่ซ่อนอยู่ในบัญชีค่าใช้จ่ายทั่วไป",
    )
    is_interest = fields.Boolean(string="เป็นบัญชีดอกเบี้ยจ่าย")
    is_tax = fields.Boolean(string="เป็นบัญชีภาษีเงินได้")
    is_debt = fields.Boolean(
        string="เป็นบัญชีเงินกู้ / หนี้สินมีดอกเบี้ย",
        help="ใช้คำนวณ Net Debt = ยอดบัญชีเหล่านี้ − เงินสด",
    )
    is_inventory = fields.Boolean(
        string="เป็นบัญชีสินค้าคงเหลือ",
        help="ใช้คิด Quick Ratio (สินทรัพย์หมุนเวียน − สินค้าคงเหลือ)",
    )

    _sql_constraints = [
        ("bsf_ext_account_code_uniq", "unique(company_id, code)",
         "มีบัญชีรหัสนี้ของบริษัทนี้อยู่แล้ว — แก้ไขรายการเดิมแทน"),
    ]

    @api.depends("code", "name")
    def _compute_display_name(self):
        for account in self:
            account.display_name = "%s %s" % (
                account.code or "?", account.name or "")

    @api.constrains("account_type", "is_debt", "is_inventory")
    def _check_flags(self):
        """ธงที่ขัดกับประเภทบัญชีทำให้ Net Debt / Quick Ratio เพี้ยนแบบเงียบ ๆ"""
        for account in self:
            if account.is_debt and not account.account_type.startswith(
                    "liability"):
                raise ValidationError(
                    "บัญชี %s: ธง 'เงินกู้' ใช้ได้เฉพาะบัญชีประเภทหนี้สิน "
                    "(ประเภทปัจจุบัน: %s)"
                    % (account.display_name, account.account_type))
            if account.is_inventory and not account.account_type.startswith(
                    "asset"):
                raise ValidationError(
                    "บัญชี %s: ธง 'สินค้าคงเหลือ' ใช้ได้เฉพาะบัญชีประเภทสินทรัพย์"
                    % account.display_name)

    @api.model
    def resolve_many(self, company, rows):
        """{code: id} ของทุกแถวใน rows — หาเป็นชุดและสร้างที่ขาดเป็นชุดเดียว

        กติกาเหมือน `resolve` ทุกข้อ (รหัสซ้ำในผังเดียวกันไม่มี, บัญชีใหม่ที่
        ไม่บอกประเภท = error) แต่ Trial Balance หนึ่งงวดมีได้หลายร้อยบัญชี
        การเรียก `resolve` ในลูปจึงเท่ากับ select+insert อย่างละหลายร้อยครั้ง

        rows: list ของ {"code", "name", "account_type"}
        """
        codes = [r["code"] for r in rows if r.get("code")]
        if not codes:
            return {}
        by_code = {
            row["code"]: row["id"]
            for row in self.search_read(
                [("company_id", "=", company.id), ("code", "in", codes)],
                ["code"])
        }
        missing, seen = [], set()
        for r in rows:
            code = r.get("code")
            if not code or code in by_code or code in seen:
                continue
            if r.get("account_type") not in ACCOUNT_TYPE_SET:
                raise ValidationError(
                    "บัญชีรหัส %s ของ %s ยังไม่มีในผังภายนอก และไม่ได้ระบุ"
                    "ประเภทบัญชี — ต้องระบุประเภทเพื่อให้ระบบรู้ว่ายอดนี้ไป"
                    "อยู่บรรทัดไหนของงบ" % (code, company.display_name))
            seen.add(code)
            missing.append({
                "company_id": company.id,
                "code": code,
                "name": r.get("name") or code,
                "account_type": r["account_type"],
            })
        for account in self.create(missing) if missing else self.browse():
            by_code[account.code] = account.id
        return by_code

    @api.model
    def resolve(self, company, code, name=None, account_type=None):
        """หาบัญชีจากรหัส สร้างให้ถ้ายังไม่มี — จุดเข้าร่วมของ wizard และ API sync

        คืน record เสมอ; ยกเว้นกรณีบัญชีใหม่ที่ไม่ได้บอก account_type มาด้วย
        ซึ่ง caller ต้องดักเองก่อน (ไม่มีประเภท = ไม่รู้ว่าไปบรรทัดไหนของงบ)"""
        account = self.search([
            ("company_id", "=", company.id), ("code", "=", code),
        ], limit=1)
        if account:
            return account
        if account_type not in ACCOUNT_TYPE_SET:
            raise ValidationError(
                "บัญชีรหัส %s ของ %s ยังไม่มีในผังภายนอก และไม่ได้ระบุประเภทบัญชี "
                "— ต้องระบุประเภทเพื่อให้ระบบรู้ว่ายอดนี้ไปอยู่บรรทัดไหนของงบ"
                % (code, company.display_name))
        return self.create({
            "company_id": company.id,
            "code": code,
            "name": name or code,
            "account_type": account_type,
        })
