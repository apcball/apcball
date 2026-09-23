# -*- coding: utf-8 -*-
from odoo import api, fields, models


class BsfConfig(models.Model):
    """ค่าตั้งต้นการเงินต่อบริษัท — ตัวเลขที่ ERP ไม่มี (เพดานเงินสดขั้นต่ำ,
    เป้า D/E, mapping บัญชีสำหรับ EBITDA/หนี้สิน) ต้องกรอกที่นี่ก่อน
    CFO Cockpit ถึงจะคำนวณครบทุกการ์ด"""

    _name = "biz.smart.finance.config"
    _description = "Smart Finance Settings (per company)"
    _rec_name = "company_id"

    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", store=True, readonly=True,
    )

    # ---- เป้าหมาย / เพดาน ----
    min_cash_requirement = fields.Monetary(
        string="เงินสดขั้นต่ำ (Minimum Cash)", currency_field="currency_id",
        help="เส้นแดงในกราฟ 13-Week Cash Forecast — ต่ำกว่านี้ระบบจะแจ้งเตือน",
    )
    operating_buffer_pct = fields.Float(
        string="Operating Buffer เหนือขั้นต่ำ (%)", default=10.0,
        help="เส้นประเทาในกราฟ 13-Week Cash Forecast = เงินสดขั้นต่ำ x (1 + %นี้)",
    )
    bank_alloc_history_months = fields.Integer(
        string="ช่วงประวัติที่ใช้กระจายเงินรายธนาคาร (เดือน)", default=6,
        help="ใช้สัดส่วนเงินเข้า/ออกจริงย้อนหลังกี่เดือน ในการกระจายเงินเข้า-ออก "
             "13 สัปดาห์ไปแต่ละธนาคาร (ธนาคารที่ตั้งสัดส่วนทับเองไม่ใช้ค่านี้)",
    )
    net_debt_equity_target = fields.Float(
        string="เป้า Net Debt / Equity (เท่า)", default=1.0,
    )
    dso_target_days = fields.Integer(string="เป้า DSO (วัน)", default=60)
    margin_leakage_alert_pct = fields.Float(
        string="เพดาน Margin Leakage (%)", default=5.0,
        help="ถ้ากำไรคาดการณ์หลุดจากงบเกิน % นี้ จะขึ้นเป็นความเสี่ยงอัตโนมัติ",
    )
    include_sales_to_cash = fields.Boolean(
        string="รวม Sales to Cash ในประมาณการเงินสด", default=False,
        help="นำใบสั่งขายที่ยืนยันแล้วและยังไม่ออกใบแจ้งหนี้มาคาดการณ์เงินรับ",
    )

    # ---- ตัวคูณ scenario (Risk Radar: Downside / Stress) ----
    downside_collection_delay_pct = fields.Float(
        string="Downside: เงินเข้าเลื่อน (%)", default=20.0,
        help="สัดส่วนเงินเข้าที่เลื่อนออกไป 2 สัปดาห์ในโหมด Downside",
    )
    downside_margin_hit_pct = fields.Float(
        string="Downside: margin หด (pp)", default=2.0,
    )
    stress_collection_delay_pct = fields.Float(
        string="Stress: เงินเข้าเลื่อน (%)", default=40.0,
        help="สัดส่วนเงินเข้าที่เลื่อนออกไป 4 สัปดาห์ในโหมด Stress",
    )
    stress_margin_hit_pct = fields.Float(
        string="Stress: margin หด (pp)", default=5.0,
    )

    # ---- สมมติฐานเพิ่มเติมของแท็บ Risk & Scenarios ----
    # สองตัวบนสุด (เงินเข้าเลื่อน / margin หด) เป็นตัวคูณที่ **ทุกแท็บ** ใช้จริง
    # ส่วนชุดนี้ใช้เฉพาะ Key Outcome / Sensitivity ของแท็บ Risk — แท็บอื่น
    # (Cash / Forecast / Margin) ไม่ได้เอาไปคิดซ้ำ จึงต้องเขียนกำกับบนจอด้วย
    downside_material_cost_pct = fields.Float(
        string="Downside: ต้นทุนวัสดุ +(%)", default=5.0,
        help="ต้นทุนงานโครงการ (BOQ/PO/งานขายที่ยังไม่เซ็น) แพงขึ้นกี่ %",
    )
    downside_interest_rate_bps = fields.Integer(
        string="Downside: ดอกเบี้ย +(bps)", default=100,
        help="อัตราดอกเบี้ยที่เพิ่มขึ้นของหนี้มีดอกเบี้ย (100 bps = 1.00%)",
    )
    downside_booking_conversion_pct = fields.Float(
        string="Downside: อัตราปิดงานขายลด (%)", default=10.0,
        help="งานขายที่ยังไม่เซ็น (pipeline) ปิดได้น้อยลงกี่ % ของยอดถ่วงน้ำหนัก",
    )
    downside_install_delay_days = fields.Integer(
        string="Downside: งานติดตั้งช้า (วัน)", default=30,
        help="งานใหม่เริ่ม/ส่งมอบช้าลงกี่วัน — เลื่อนทั้งเงินเข้าและการรับรู้รายได้",
    )
    downside_fx_move_pct = fields.Float(
        string="Downside: ค่าเงินผันผวน (%)", default=5.0,
        help="สินทรัพย์ที่ถือในสกุลต่างจากสกุลนำเสนอเปลี่ยนค่ากี่ %",
    )
    stress_material_cost_pct = fields.Float(
        string="Stress: ต้นทุนวัสดุ +(%)", default=10.0,
    )
    stress_interest_rate_bps = fields.Integer(
        string="Stress: ดอกเบี้ย +(bps)", default=200,
    )
    stress_booking_conversion_pct = fields.Float(
        string="Stress: อัตราปิดงานขายลด (%)", default=25.0,
    )
    stress_install_delay_days = fields.Integer(
        string="Stress: งานติดตั้งช้า (วัน)", default=60,
    )
    stress_fx_move_pct = fields.Float(
        string="Stress: ค่าเงินผันผวน (%)", default=10.0,
    )

    # ---- สมมติฐานของแท็บ Forecast (พยากรณ์รายเดือน) ----
    forecast_horizon_months = fields.Integer(
        string="ช่วงพยากรณ์ (เดือน)", default=12,
        help="ความยาวกริดรายเดือนของแท็บ Forecast — รับ 6 ถึง 18 เดือน "
             "(เงินที่ตกหลังช่วงนี้ไม่หาย แต่ถูกรวมไว้ในคอลัมน์ 'หลังจากนี้')",
    )
    pipeline_default_margin_pct = fields.Float(
        string="กำไรขั้นต้นตั้งต้นของงานขาย (%)", default=30.0,
        help="ใช้ประมาณต้นทุนของดีลที่ยังไม่เซ็น เมื่อดีลนั้นไม่ได้ระบุเอง",
    )
    pipeline_cost_lag_months = fields.Integer(
        string="ต้นทุนงานขายเริ่มหลังเซ็น (เดือน)", default=0,
        help="0 = เริ่มมีต้นทุนเดือนเดียวกับที่เซ็น",
    )

    # ---- mapping บัญชี (account_type เดี่ยว ๆ แยกดอกเบี้ย/ภาษี/เงินกู้ไม่ได้) ----
    depreciation_account_ids = fields.Many2many(
        "account.account", relation="bsf_config_depr_account_rel",
        string="บัญชีค่าเสื่อม/ตัดจำหน่าย",
        domain="[('company_id', '=', company_id)]",
        help="เพิ่มเติมจากบัญชีประเภท 'ค่าเสื่อมราคา' ที่ระบบบวกกลับให้อยู่แล้ว",
    )
    interest_account_ids = fields.Many2many(
        "account.account", relation="bsf_config_int_account_rel",
        string="บัญชีดอกเบี้ยจ่าย",
        domain="[('company_id', '=', company_id)]",
    )
    tax_account_ids = fields.Many2many(
        "account.account", relation="bsf_config_taxx_account_rel",
        string="บัญชีภาษีเงินได้",
        domain="[('company_id', '=', company_id)]",
    )
    debt_account_ids = fields.Many2many(
        "account.account", relation="bsf_config_debt_account_rel",
        string="บัญชีเงินกู้ / หนี้สินมีดอกเบี้ย",
        domain="[('company_id', '=', company_id)]",
        help="ใช้คำนวณ Net Debt = ยอดบัญชีเหล่านี้ − เงินสด",
    )

    # ---- Mapping บัญชีของงบแสดงฐานะการเงิน (แยกบรรทัดย่อยที่ account_type
    #      เดี่ยว ๆ แยกไม่ได้ เช่น เงินให้กู้บริษัทย่อย / รายได้รับล่วงหน้า /
    #      ส่วนของหนี้ยาวที่ถึงกำหนดในปีนี้ / ทุนชำระแล้ว vs สำรองตามกฎหมาย)
    #      บรรทัด "อื่น ๆ" ของแต่ละหมวด = ยอดที่เหลือของ account_type นั้นหลัง
    #      หักบัญชีที่ map ไว้ทุกช่องแล้ว — เป็น Odoo account เท่านั้น ----
    bs_loans_subsidiaries_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_loans_sub_rel",
        string="เงินให้กู้ยืมแก่บริษัทย่อย",
        domain="[('company_id', '=', company_id)]",
    )
    bs_lt_deposit_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_lt_deposit_rel",
        string="เงินฝากสถาบันการเงินระยะยาว",
        domain="[('company_id', '=', company_id)]",
    )
    bs_bank_overdraft_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_bank_od_rel",
        string="เงินเบิกเกินบัญชี/เงินกู้ยืมระยะสั้นจากสถาบันการเงิน",
        domain="[('company_id', '=', company_id)]",
    )
    bs_deferred_revenue_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_def_rev_rel",
        string="รายได้รับล่วงหน้า",
        domain="[('company_id', '=', company_id)]",
    )
    bs_related_party_st_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_rp_st_rel",
        string="เงินกู้ยืมระยะสั้นจากกิจการที่เกี่ยวข้องกัน",
        domain="[('company_id', '=', company_id)]",
    )
    bs_current_ltd_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_cur_ltd_rel",
        string="ส่วนของหนี้สินระยะยาวที่ถึงกำหนดชำระในหนึ่งปี",
        domain="[('company_id', '=', company_id)]",
    )
    bs_current_lease_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_cur_lease_rel",
        string="ส่วนของหนี้สินตามสัญญาเช่าที่ถึงกำหนดชำระในหนึ่งปี",
        domain="[('company_id', '=', company_id)]",
    )
    bs_deferred_tax_liability_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_dtl_rel",
        string="หนี้สินภาษีเงินได้รอตัดบัญชี",
        domain="[('company_id', '=', company_id)]",
    )
    bs_lt_debt_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_lt_debt_rel",
        string="หนี้สินระยะยาว - สุทธิจากส่วนที่ถึงกำหนดชำระในหนึ่งปี",
        domain="[('company_id', '=', company_id)]",
    )
    bs_related_party_lt_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_rp_lt_rel",
        string="เงินกู้ยืมระยะยาวจากกิจการที่เกี่ยวข้องกัน",
        domain="[('company_id', '=', company_id)]",
    )
    bs_employee_benefit_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_emp_ben_rel",
        string="ประมาณการหนี้สินผลประโยชน์พนักงาน",
        domain="[('company_id', '=', company_id)]",
    )
    bs_lease_liability_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_lease_lt_rel",
        string="หนี้สินตามสัญญาเช่า (ไม่หมุนเวียน)",
        domain="[('company_id', '=', company_id)]",
    )
    bs_paid_in_capital_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_paid_in_rel",
        string="ทุนที่ออกและชำระแล้ว",
        domain="[('company_id', '=', company_id)]",
    )
    bs_legal_reserve_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_bs_legal_rsv_rel",
        string="สำรองตามกฎหมาย",
        domain="[('company_id', '=', company_id)]",
    )
    cf_dividend_account_ids = fields.Many2many(
        "account.account", relation="bsf_cfg_cf_dividend_rel",
        string="เงินปันผลจ่าย / เจ้าหนี้เงินปันผล",
        domain="[('company_id', '=', company_id)]",
        help="บัญชีที่เดบิตตอนประกาศ/จ่ายปันผล — งบกระแสเงินสดใช้แยกบรรทัด "
             "'เงินปันผลจ่าย' ออกจากการเปลี่ยนแปลงของส่วนของผู้ถือหุ้นอื่น",
    )

    # ---- แหล่งข้อมูล Inventory / Financial Ratios (ต่อบริษัท) ----
    gl_source = fields.Selection(
        [("odoo", "Odoo (account.move.line)"), ("external", "ระบบภายนอก")],
        string="แหล่งข้อมูลบัญชีแยกประเภท (GL)", required=True, default="odoo",
        help="ระบบภายนอก = งบดุล/งบกำไรขาดทุน/งบกระแสเงินสด/Compare/Overview "
             "อ่านจาก Trial Balance ภายนอก (External GL) แทนบรรทัด "
             "account.move.line — ตั้งได้ละเอียดถึงระดับเดือนที่ 'ทะเบียนงวด' "
             "(Monthly Close Cockpit) ค่านี้เป็นเพียงค่าตั้งต้นของเดือนที่ยังไม่ "
             "ตั้งไว้เป็นการเฉพาะ",
    )
    inventory_source = fields.Selection(
        [("odoo", "Odoo (stock valuation)"), ("external", "ระบบภายนอก")],
        string="แหล่งข้อมูลสินค้าคงเหลือ", required=True, default="odoo",
        help="ระบบภายนอก = อ่านจากตาราง External Figures "
             "(กรอกมือ / นำเข้าไฟล์ / API sync)",
    )
    ratio_source = fields.Selection(
        [("odoo", "Odoo (GL)"), ("external", "ระบบภายนอก")],
        string="แหล่งข้อมูลอัตราส่วนการเงิน", required=True, default="odoo",
        help="ระบบภายนอก = คิดอัตราส่วนจากตัวเลขงบใน External Figures "
             "แทนยอด GL ใน Odoo",
    )
    invoice_source = fields.Selection(
        [("odoo", "Odoo (account.move)"), ("external", "ระบบภายนอก")],
        string="แหล่งข้อมูลใบแจ้งหนี้/บิลค้าง", required=True, default="odoo",
        help="ระบบภายนอก = อ่านลูกหนี้/เจ้าหนี้คงค้างจากตาราง External "
             "Invoices แทนบรรทัด AR/AP ใน GL — มีผลกับ AR aging, "
             "AP & Payment Plan, Cash Forecast และกรวย Sales to Cash",
    )
    budget_source = fields.Selection(
        [("odoo", "Odoo (Budget)"), ("external", "ระบบภายนอก")],
        string="แหล่งข้อมูลงบศูนย์ต้นทุน", required=True, default="odoo",
        help="ระบบภายนอก = อ่านงบจากตาราง External Budgets แทน "
             "crossovered.budget.lines ในแท็บ Controlling",
    )
    inventory_account_ids = fields.Many2many(
        "account.account", relation="bsf_config_inv_account_rel",
        string="บัญชีสินค้าคงเหลือ",
        domain="[('company_id', '=', company_id)]",
        help="บัญชีประเภท 'สินทรัพย์หมุนเวียน' แยกสต๊อกเองไม่ได้ — ใช้คิด "
             "Quick Ratio และกระทบยอดมูลค่า SVL กับ GL",
    )
    ext_company_code = fields.Char(
        string="รหัสบริษัทในระบบภายนอก",
        help="ใช้ตอน API sync ดึงตัวเลขจากระบบภายนอก",
    )

    _sql_constraints = [
        ("bsf_config_company_uniq", "unique(company_id)",
         "ตั้งค่า Smart Finance ได้บริษัทละ 1 ชุดเท่านั้น"),
    ]

    def action_sync_external(self):
        """ปุ่มบนฟอร์ม — ดึงตัวเลขจากระบบภายนอกของบริษัทนี้เดี๋ยวนี้"""
        self.ensure_one()
        return self.env["biz.smart.finance.source"].action_sync(
            company_ids=self.company_id.ids)

    @api.model
    def get_for_companies(self, company_ids):
        """คืน {company_id: record} เฉพาะบริษัทที่มี config แล้ว"""
        records = self.search([("company_id", "in", list(company_ids))])
        return {rec.company_id.id: rec for rec in records}
