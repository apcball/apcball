# -*- coding: utf-8 -*-
"""CFO Cockpit data engine.

กติกาสำคัญ (อย่าแก้โดยไม่อ่าน):

* คืนค่าเป็น JSON-serializable เท่านั้น — วันที่แปลงเป็น str, ไม่มี recordset
* **เงินทุกช่องเป็น THB ดิบ** (ไม่หาร 1e6) — ฝั่ง JS มี unit toggle THB/ล้านบาท
  จึง scale ที่ JS ที่เดียว; เปอร์เซ็นต์ปัด round(x, 1) จากฝั่งนี้
* ลำดับสิทธิ์ห้ามสลับ: gate has_group ก่อน → ตรวจขอบเขตบริษัทกับ
  user.company_ids (สิทธิ์จริง ไม่ใช่ env.companies) → แล้วค่อย sudo อ่านข้อมูล
  (viewer การเงินไม่จำเป็นต้องมี ACL บัญชี — จอนี้แสดงยอดรวมที่ผ่าน gate แล้ว)
* ห้าม strftime("%b") — locale production เป็นไทย ให้ประกอบ label เอง
* ฟิลด์ compute ที่ไม่ stored (gate1/gate5 margin, plan-line residual ฯลฯ)
  ห้ามอยู่ในโดเมน search — search ด้วยเงื่อนไข stored แล้วอ่าน/กรองใน Python
"""
import bisect
import calendar
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .bsf_deal import OPEN_STAGES

REVENUE_TYPES = ("income", "income_other")
COGS_TYPES = ("expense_direct_cost",)
OPEX_TYPES = ("expense", "expense_depreciation")
PL_TYPES = REVENUE_TYPES + COGS_TYPES + OPEX_TYPES
EQUITY_TYPES = ("equity", "equity_unaffected")
AR_TYPE = "asset_receivable"
AP_TYPE = "liability_payable"

# ถังสำหรับ Financial Ratios (สภาพคล่อง/หนี้สิน/ประสิทธิภาพ)
CA_TYPES = ("asset_cash", AR_TYPE, "asset_current", "asset_prepayments")
CL_TYPES = (AP_TYPE, "liability_credit_card", "liability_current")
ASSET_TYPES = CA_TYPES + ("asset_fixed", "asset_non_current")
LIAB_TYPES = CL_TYPES + ("liability_non_current",)

# metric ภายนอกขั้นต่ำที่ทำให้ ratio ครบทุกกลุ่ม — ใช้รายงาน missing ต่อบริษัท
EXT_CORE_KEYS = (
    "current_assets", "current_liabilities", "total_assets",
    "total_liabilities", "equity", "revenue_ytd", "cogs_ytd",
    "net_profit_ytd",
)

# โครงงบแสดงฐานะการเงินแบบ waterfall (แยกหมุนเวียน/ไม่หมุนเวียน + บรรทัดสรุป)
#   (kind, sec, key, label, src)
#   kind "line"     = แถวรายบัญชี (กาง/drill ได้)  src บอกที่มาบัญชี:
#       ("type",    (atypes...))  บัญชีตาม account_type
#       ("type_ex", (atypes...))  account_type ยกเว้น id ที่ map ไปบรรทัดอื่นแล้ว
#       ("map",     "<key ใน bs_map_ids>")  บัญชีที่ผูกไว้ใน Settings
#       ("equity_plug",)          −Σ equity ที่ไม่ถูก map − Σ P&L สะสม (กำไรสะสม)
#   kind "subtotal" = บรรทัดสรุป  src:
#       ("lines", "<sec>")        ผลรวมของบรรทัด line ในหมวดนั้น
#       ("sum", ("<key>", ...))   ผลรวมของบรรทัดสรุปที่ระบุ
#   sec: ca=สินทรัพย์หมุนเวียน nca=ไม่หมุนเวียน cl=หนี้สินหมุนเวียน
#        ncl=หนี้สินไม่หมุนเวียน eq=ส่วนของผู้ถือหุ้น (+ assets/liab/liab_eq ของ subtotal)
#   sign: ca/nca = +1 (เดบิต), cl/ncl/eq = -1 (เครดิต กลับเครื่องหมาย)
BS_WATERFALL = [
    # ---- สินทรัพย์หมุนเวียน ----
    ("line", "ca", "asset_cash", "เงินสดและรายการเทียบเท่าเงินสด",
     ("type", ("asset_cash",))),
    ("line", "ca", "asset_receivable", "ลูกหนี้การค้าและลูกหนี้อื่น",
     ("type", (AR_TYPE,))),
    ("line", "ca", "inventory", "สินค้าคงเหลือ", ("map", "inventory")),
    ("line", "ca", "loans_subsidiaries", "เงินให้กู้ยืมแก่บริษัทย่อย",
     ("map", "loans_subsidiaries")),
    ("line", "ca", "other_current_assets", "สินทรัพย์หมุนเวียนอื่น",
     ("type_ex", ("asset_current", "asset_prepayments"))),
    ("subtotal", "ca", "total_ca", "รวมสินทรัพย์หมุนเวียน", ("lines", "ca")),
    # ---- สินทรัพย์ไม่หมุนเวียน ----
    ("line", "nca", "asset_fixed",
     "ที่ดิน อาคารและอุปกรณ์ / สินทรัพย์ไม่มีตัวตน - สุทธิ",
     ("type", ("asset_fixed",))),
    ("line", "nca", "lt_deposits", "เงินฝากสถาบันการเงินระยะยาว",
     ("map", "lt_deposit")),
    ("line", "nca", "other_noncurrent_assets", "สินทรัพย์ไม่หมุนเวียนอื่น",
     ("type_ex", ("asset_non_current",))),
    ("subtotal", "nca", "total_nca", "รวมสินทรัพย์ไม่หมุนเวียน",
     ("lines", "nca")),
    ("subtotal", "assets", "total_assets", "รวมสินทรัพย์",
     ("sum", ("total_ca", "total_nca"))),
    # ---- หนี้สินหมุนเวียน ----
    ("line", "cl", "bank_overdraft",
     "เงินเบิกเกินบัญชีและเงินกู้ยืมระยะสั้นจากสถาบันการเงิน",
     ("map", "bank_overdraft")),
    ("line", "cl", "liability_payable", "เจ้าหนี้การค้าและเจ้าหนี้อื่น",
     ("type", (AP_TYPE,))),
    ("line", "cl", "deferred_revenue", "รายได้รับล่วงหน้า",
     ("map", "deferred_revenue")),
    ("line", "cl", "related_party_st",
     "เงินกู้ยืมระยะสั้นจากกิจการที่เกี่ยวข้องกัน", ("map", "related_party_st")),
    ("line", "cl", "current_ltd",
     "ส่วนของหนี้สินระยะยาวที่ถึงกำหนดชำระภายในหนึ่งปี", ("map", "current_ltd")),
    ("line", "cl", "current_lease",
     "ส่วนของหนี้สินตามสัญญาเช่าที่ถึงกำหนดชำระภายในหนึ่งปี",
     ("map", "current_lease")),
    ("line", "cl", "deferred_tax_liability", "หนี้สินภาษีเงินได้รอตัดบัญชี",
     ("map", "deferred_tax_liability")),
    ("line", "cl", "other_current_liab", "หนี้สินหมุนเวียนอื่น",
     ("type_ex", ("liability_current", "liability_credit_card"))),
    ("subtotal", "cl", "total_cl", "รวมหนี้สินหมุนเวียน", ("lines", "cl")),
    # ---- หนี้สินไม่หมุนเวียน ----
    ("line", "ncl", "lt_debt",
     "หนี้สินระยะยาว - สุทธิจากส่วนที่ถึงกำหนดชำระในหนึ่งปี", ("map", "lt_debt")),
    ("line", "ncl", "related_party_lt",
     "เงินกู้ยืมระยะยาวจากกิจการที่เกี่ยวข้องกัน", ("map", "related_party_lt")),
    ("line", "ncl", "employee_benefit", "ประมาณการหนี้สินผลประโยชน์พนักงาน",
     ("map", "employee_benefit")),
    ("line", "ncl", "lease_liability", "หนี้สินตามสัญญาเช่า",
     ("map", "lease_liability")),
    ("line", "ncl", "other_noncurrent_liab", "หนี้สินไม่หมุนเวียนอื่น",
     ("type_ex", ("liability_non_current",))),
    ("subtotal", "ncl", "total_ncl", "รวมหนี้สินไม่หมุนเวียน",
     ("lines", "ncl")),
    ("subtotal", "liabilities", "total_liab", "รวมหนี้สิน",
     ("sum", ("total_cl", "total_ncl"))),
    # ---- ส่วนของผู้ถือหุ้น ----
    ("line", "eq", "paid_in_capital", "ทุนที่ออกและชำระแล้ว",
     ("map", "paid_in_capital")),
    ("line", "eq", "legal_reserve", "สำรองตามกฎหมาย", ("map", "legal_reserve")),
    ("line", "eq", "retained_earnings", "กำไรสะสมที่ยังไม่ได้จัดสรร",
     ("equity_plug",)),
    ("subtotal", "eq", "total_equity", "รวมส่วนของผู้ถือหุ้น", ("lines", "eq")),
    ("subtotal", "liab_eq", "total_liab_eq",
     "รวมหนี้สินและส่วนของผู้ถือหุ้น", ("sum", ("total_liab", "total_equity"))),
]

# บรรทัด line ของงบดุลที่ map บัญชีใน Settings (key ใน bs_map_ids ← config M2M)
BS_MAP_FIELDS = {
    "loans_subsidiaries": "bs_loans_subsidiaries_account_ids",
    "lt_deposit": "bs_lt_deposit_account_ids",
    "bank_overdraft": "bs_bank_overdraft_account_ids",
    "deferred_revenue": "bs_deferred_revenue_account_ids",
    "related_party_st": "bs_related_party_st_account_ids",
    "current_ltd": "bs_current_ltd_account_ids",
    "current_lease": "bs_current_lease_account_ids",
    "deferred_tax_liability": "bs_deferred_tax_liability_account_ids",
    "lt_debt": "bs_lt_debt_account_ids",
    "related_party_lt": "bs_related_party_lt_account_ids",
    "employee_benefit": "bs_employee_benefit_account_ids",
    "lease_liability": "bs_lease_liability_account_ids",
    "paid_in_capital": "bs_paid_in_capital_account_ids",
    "legal_reserve": "bs_legal_reserve_account_ids",
}
BS_SEC_SIGN = {"ca": 1, "nca": 1, "cl": -1, "ncl": -1, "eq": -1}

# โครงงบกำไรขาดทุนแบบ waterfall — เรียงตามงบจริง (Revenue → … → Net income)
#   kind "line"  = แถวรายบัญชี (กาง/drill ได้)  src บอกที่มาบัญชี:
#       ("type",    (atypes...))  บัญชีตาม account_type
#       ("type_ex", (atypes...))  account_type ยกเว้น id ที่ map เป็นค่าเสื่อม/ดอกเบี้ย/ภาษี
#       ("map",     "dep"|"int"|"tax")  บัญชีที่ผูกไว้ใน config (+ type ค่าเสื่อม)
#   kind "total" = บรรทัดสรุป อ่านจาก pl[key] ตรง ๆ (key มาจาก _pl_from_balances)
#   sign: -1 = ฝั่งรายได้ (กลับเครื่องหมาย balance), +1 = ฝั่งค่าใช้จ่าย
PNL_WATERFALL = [
    ("line",  "revenue_op",   "รายได้จากการขายและบริการ",   -1, ("type", ("income",))),
    ("line",  "cogs",         "ต้นทุนขายและบริการ",          1, ("type", COGS_TYPES)),
    ("total", "gross_op",     "กำไรขั้นต้น",                 0,  None),
    ("line",  "sga",          "ค่าใช้จ่ายในการขายและบริหาร",  1, ("type_ex", OPEX_TYPES)),
    ("line",  "other_income", "รายได้อื่น",                  -1, ("type", ("income_other",))),
    ("total", "ebitda",       "EBITDA",                      0,  None),
    ("line",  "depreciation", "ค่าเสื่อมราคาและค่าตัดจำหน่าย", 1, ("map", "dep")),
    ("total", "ebit",         "EBIT (กำไรจากการดำเนินงาน)",   0,  None),
    ("line",  "interest",     "ดอกเบี้ยจ่าย",                 1, ("map", "int")),
    ("total", "pretax",       "กำไร (ขาดทุน) ก่อนภาษี",       0,  None),
    ("line",  "tax",          "ภาษีเงินได้",                  1, ("map", "tax")),
    ("total", "net",          "กำไร (ขาดทุน) สุทธิ",          0,  None),
]

# ถังของงบกระแสเงินสดทางอ้อม (ดู _build_statements — identity ปิดที่ asset_cash)
CF_OTHER_CA_TYPES = ("asset_current", "asset_prepayments")
CF_OTHER_CL_TYPES = ("liability_credit_card", "liability_current")
CF_INVEST_TYPES = ("asset_fixed", "asset_non_current")
CF_FIN_LIAB_TYPES = ("liability_non_current",)

# บัญชีหนี้มีดอกเบี้ย/ลีส/ลงทุน ของงบกระแสเงินสด — ยกมาจาก bs_map_ids (BS mapping)
CF_DEBT_KEYS = ("bank_overdraft", "current_ltd", "lt_debt",
                "related_party_st", "related_party_lt")
CF_LEASE_KEYS = ("current_lease", "lease_liability")
CF_INVEST_OTHER_KEYS = ("lt_deposit", "loans_subsidiaries")

# โครงงบกระแสเงินสดทางอ้อมแบบ waterfall — (kind, sec, key, label, src)
#   kind "line" — src บอกที่มา (cash effect = -(Σ balance งวดนี้ − Σ balance ต้นงวด)):
#     ("pl", "net"|"depreciation")       จาก pl_total (บวกกลับรายการไม่ใช่เงินสด)
#     ("d_type", (atypes,))              Δ ของ account_type
#     ("d_type_ex", (atypes,), (keys,))  Δ ของ type ยกเว้น id ที่ map เป็น bs_map_ids[keys]
#     ("d_ids", (bs_map keys,))          Δ ของบัญชีที่ map ไว้
#     ("map", "cf_dividend")             Δ ของบัญชีเงินปันผล (+ ธง configured)
#     ("capex",)                         d_type((asset_fixed,)) − pl.depreciation
#     ("equity_fin",)                    Δ equity (ยกเว้นปันผล) + Δ หนี้ยาว (ยกเว้น debt/lease)
#   kind "subtotal" — src: ("lines", "<sec>") | ("sum", (key, ...))
#   sec: cfo / cfi / cff  (sign ของ cash effect รวมอยู่ในสูตร src แล้ว)
CF_WATERFALL = [
    ("line", "cfo", "net_income", "กำไร (ขาดทุน) สุทธิ", ("pl", "net")),
    ("line", "cfo", "dna", "บวกกลับ: ค่าเสื่อมราคาและค่าตัดจำหน่าย",
     ("pl", "depreciation")),
    ("line", "cfo", "d_ar", "ลูกหนี้การค้า (เพิ่มขึ้น) ลดลง",
     ("d_type", (AR_TYPE,))),
    ("line", "cfo", "d_inv", "สินค้าคงเหลือ (เพิ่มขึ้น) ลดลง",
     ("d_ids", ("inventory",))),
    ("line", "cfo", "d_ap", "เจ้าหนี้การค้า เพิ่มขึ้น (ลดลง)",
     ("d_type", (AP_TYPE,))),
    ("line", "cfo", "other_cfo", "รายการทุนหมุนเวียนอื่น สุทธิ",
     ("wc_other",)),
    ("subtotal", "cfo", "total_cfo",
     "กระแสเงินสดสุทธิจากกิจกรรมดำเนินงาน (CFO)", ("lines", "cfo")),
    ("line", "cfi", "capex",
     "ลงทุนในที่ดิน อาคารและอุปกรณ์ / สินทรัพย์ไม่มีตัวตน", ("capex",)),
    ("line", "cfi", "other_cfi", "กระแสเงินสดจากกิจกรรมลงทุนอื่น",
     ("invest_other",)),
    ("subtotal", "cfi", "total_cfi",
     "กระแสเงินสดสุทธิจากกิจกรรมลงทุน (CFI)", ("lines", "cfi")),
    ("line", "cff", "dividends", "เงินปันผลจ่าย", ("map", "cf_dividend")),
    ("line", "cff", "net_debt", "เงินกู้ยืม เพิ่มขึ้น (ชำระคืน) สุทธิ",
     ("d_ids", CF_DEBT_KEYS)),
    ("line", "cff", "lease", "หนี้สินตามสัญญาเช่า เพิ่มขึ้น (ลดลง)",
     ("d_ids", CF_LEASE_KEYS)),
    ("line", "cff", "other_cff", "กระแสเงินสดจากกิจกรรมจัดหาเงินอื่น",
     ("equity_fin",)),
    ("subtotal", "cff", "total_cff",
     "กระแสเงินสดสุทธิจากกิจกรรมจัดหาเงิน (CFF)", ("lines", "cff")),
    ("subtotal", "net", "net_change", "เงินสดเพิ่มขึ้น (ลดลง) สุทธิ",
     ("sum", ("total_cfo", "total_cfi", "total_cff"))),
]

# กลุ่มขั้นตอน funnel (ดู biz_smart_project/models/pm_constants.py)
PRODUCTION_KINDS = ("produce", "pr", "po", "sub_pr", "sub_po")
INSTALL_KINDS = ("install", "inspect")

WEEK_COUNT = 13
AP_CAL_WEEKS = 6

# ห้าม strftime("%b") — locale production เป็นไทย จึงประกอบชื่อเดือนเอง
MONTH_ABBR = [
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]
SCENARIO_SHIFT_WEEKS = {"downside": 2, "stress": 4}
# แท็บ Forecast เป็นกริดรายเดือน จึงเลื่อนเป็นเดือน (2/4 สัปดาห์ปัดเป็น 1/2 เดือน)
SCENARIO_SHIFT_MONTHS = {"downside": 1, "stress": 2}

# ช่วงเวลาที่แท็บ Risk & Scenarios ให้เลือกดู (เดือน) — engine คำนวณทุกช่วง
# ให้ครบตั้งแต่ตอนโหลด แล้ว frontend สลับดูได้โดยไม่ต้องยิงเซิร์ฟเวอร์ใหม่
RISK_HORIZONS = (3, 6, 12)

# แท็บ Cash & Liquidity — มุมมองรายธนาคาร: เกณฑ์สถานะ % การใช้วงเงิน
FACILITY_UTIL_MONITOR = 60.0
FACILITY_UTIL_RISK = 85.0
# สัดส่วนกระจายเงินเข้า/ออกรายธนาคาร ถ้าไม่มีทั้งประวัติและยอดเงินสด
BANK_ALLOC_HISTORY_DEFAULT = 6

# ขอบเขตกริดรายเดือนของแท็บ Forecast (config ต่อบริษัทเลือกได้ในช่วงนี้)
FORECAST_MONTHS_DEFAULT = 12
FORECAST_MONTHS_MIN = 6
FORECAST_MONTHS_MAX = 18

# แถวของแท็บเปรียบเทียบที่ "เพิ่มขึ้น = ดี" — นอกลิสต์นี้ (ต้นทุน ค่าใช้จ่าย
# เจ้าหนี้ หนี้สิน และเงินทุนที่จมใน AR/สต๊อก) เพิ่มขึ้นคือสัญญาณลบ จึงต้อง
# กลับสีลูกศร ตัดสินที่นี่ที่เดียวเพื่อให้จอกับไฟล์ที่ export ตรงกัน
COMPARE_GOOD_WHEN_UP = frozenset((
    # P&L
    "revenue", "revenue_op", "other_income", "gross", "gross_op",
    "ebitda", "ebit", "pretax", "net",
    # งบดุล: สินทรัพย์ + ส่วนของผู้ถือหุ้นเพิ่ม = ดี (หนี้สินเพิ่ม = ลบ)
    "asset_cash", "asset_receivable", "inventory", "loans_subsidiaries",
    "other_current_assets", "total_ca", "asset_fixed", "lt_deposits",
    "other_noncurrent_assets", "total_nca", "total_assets", "total_equity",
))

# ------------------------------------------------------------------
# แท็บ Sales Channel (วิเคราะห์ช่องทางขาย)
# ------------------------------------------------------------------
# มิติช่องทางที่เลือกได้บนจอ — (code, ชื่อมิติ, ชื่อแถวย่อยของบรรทัดรายได้)
CHANNEL_DIMS = [
    ("partner", "ลูกค้าเชน / สาขา", "สาขา"),
    ("team", "ทีมขาย", "ลูกค้า"),
    ("analytic", "ศูนย์ต้นทุน (Analytic)", "ลูกค้า"),
]
CHANNEL_DIM_CODES = tuple(code for code, _label, _sub in CHANNEL_DIMS)
CHANNEL_DIM_DEFAULT = "partner"
# ช่องทาง 0 = ยอดที่ผูกช่องทางจาก GL ไม่ได้ — ต้องเห็นบนจอ ห้ามซ่อน/ห้ามทิ้ง
CHANNEL_NONE = 0
# เพดานแถวที่ส่งขึ้นจอ — ที่เหลือยุบเป็นแถว "อื่น ๆ" (ยอดรวมไม่หาย)
CHANNEL_MAX_ROWS = 20
CHANNEL_MAX_SUB_ROWS = 30

# โครงงบกำไรขาดทุนของแท็บช่องทางขาย — (kind, key, label, sub)
#   kind "split" = บรรทัดที่กางแถวย่อยได้ (sub "channel" = แยกตามช่องทาง/สาขา,
#                  "account" = แยกตามบัญชี = "ประเภทต้นทุน" ในเวิร์กชีตต้นแบบ)
#   kind "total" = บรรทัดสรุป คิดจากบรรทัดข้างบนของช่องทางนั้น (CHANNEL_PNL_TOTALS)
#   kind "pct"   = อัตราส่วนต่อรายได้ (sub = key ของตัวตั้ง)
CHANNEL_PNL = [
    ("split", "revenue_op", "รายได้จากการขายและบริการ", "channel"),
    ("split", "cogs", "ต้นทุนขายและบริการ", "account"),
    ("total", "gross_op", "กำไรขั้นต้น", None),
    ("pct", "gross_pct", "อัตรากำไรขั้นต้น (% ของรายได้)", "gross_op"),
    ("split", "sga", "ค่าใช้จ่ายในการขายและบริหาร", "account"),
    ("pct", "sga_pct", "SG&A (% ของรายได้)", "sga"),
    ("split", "other_income", "รายได้อื่น", "account"),
    ("total", "ebitda", "EBITDA", None),
    ("split", "depreciation", "ค่าเสื่อมราคาและค่าตัดจำหน่าย", "account"),
    ("total", "ebit", "EBIT (กำไรจากการดำเนินงาน)", None),
    ("pct", "ebit_pct", "EBIT (% ของรายได้)", "ebit"),
]
# บรรทัดที่ engine แยกยอดตามช่องทางจริง (ที่เหลือเป็นบรรทัดสรุป/อัตราส่วน)
CHANNEL_PNL_LINES = ("revenue_op", "cogs", "sga", "other_income",
                     "depreciation")
# สูตรบรรทัดสรุป — ต้องตรงกับ PNL_WATERFALL ระดับบริษัททุกตัว
CHANNEL_PNL_TOTALS = {
    "gross_op": (("revenue_op", 1), ("cogs", -1)),
    "ebitda": (("gross_op", 1), ("sga", -1), ("other_income", 1)),
    "ebit": (("ebitda", 1), ("depreciation", -1)),
}

FUNNEL_STAGES = [
    ("booking", "Booking"),
    ("backlog", "Backlog"),
    ("production", "Production"),
    ("install", "Install"),
    ("invoice", "Invoice"),
    ("collection", "Collection"),
]


class BsfDashboard(models.AbstractModel):
    _name = "biz.smart.finance.dashboard"
    _description = "Smart Finance CFO Cockpit Engine"

    # ------------------------------------------------------------------
    # entry point
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, filters=None):
        self._check_access()
        # normalize ต้องรันเป็นผู้ใช้จริง (อ่าน user.company_ids) ก่อน sudo
        f = self._normalize_filters(filters or {})
        # gate + ขอบเขตบริษัทผ่านแล้ว — sudo เพื่ออ่านข้อมูลบัญชี/ขาย/ซื้อ
        # โดยไม่บังคับให้ viewer ต้องถือ ACL ของทุกโมดูล (ทุกโดเมนด้านล่าง
        # ถูก scope ด้วย company ใน f["cids"] อยู่แล้ว)
        self = self.sudo()
        shared = self._build_shared(f)
        shared["cash_forecast"] = self._build_cash_forecast(f, shared)
        # inventory ต้องมาก่อน overview/ratios — _ccc_days กับ _build_ratios
        # อ่าน DIO/มูลค่าสต๊อกจาก shared ที่ตัวนี้เขียนไว้
        inventory = self._build_inventory(f, shared)
        # margin ต้องมาก่อน overview/risk — _auto_alerts อ่าน leakage จาก shared
        margin = self._build_margin(f, shared)
        # forecast ต้องมาก่อน risk — Key Outcome / Sensitivity ของแท็บ Risk
        # ใช้ฐานรายเดือนชุดเดียวกัน (shared["fc_basis"]) ไม่คำนวณซ้ำเอง
        forecast = self._build_forecast(f, shared)
        # แท็บทั้งหมดต้องสร้างก่อน overview — control tower ย่อยตัวเลข headline
        # ของทุกแท็บมาโชว์เป็นการ์ดมิติ (ลำดับ shared mutation เดิมทุกประการ:
        # margin ก่อน forecast, inventory ก่อน ratios ฯลฯ)
        tabs = {
            "cash": self._build_cash_tab(f, shared),
            "sales": self._build_sales(f, shared),
            "margin": margin,
            # forecast ต้องมาหลัง margin — ใช้ต้นทุนคงเหลือชุดเดียวกัน (shared)
            "forecast": forecast,
            "ap": self._build_ap(f, shared),
            "risk": self._build_risk(f, shared),
            "statements": self._build_statements(f, shared),
            "controlling": self._build_controlling(f, shared),
            "inventory": inventory,
            "ratios": self._build_ratios(f, shared),
            "compare": self._build_compare(f, shared),
        }
        payload = {
            "filters": f["echo"],
            "empty_hints": self._empty_hints(f, shared),
            "overview": self._build_overview(f, shared, tabs),
            **tabs,
            # สถานะ AI ให้ frontend ตัดสินใจโชว์ปุ่ม/hint (sudo คง env.user เดิม)
            "ai": {
                "configured": self.env["biz.smart.finance.ai"].is_configured(),
                "is_manager": self.env.user.has_group(
                    "biz_smart_finance.group_bsf_manager"),
            },
            "currency_symbol": f["presentation_currency"].symbol or "",
            "updated_at": fields.Datetime.to_string(fields.Datetime.now()),
        }
        return payload

    @api.model
    def get_forecast_data(self, filters=None):
        """Payload ของแท็บ Forecast อย่างเดียว — ใช้โดย cron ภาพนิ่งรายเดือน

        `_build_forecast` ต้องการ `shared`, กริดเงินสด 13 สัปดาห์ และตัวเลข
        ต้นทุนคงเหลือจาก `_build_margin` (ผ่าน shared) เท่านั้น — อีกสิบแท็บ
        ที่ `get_dashboard_data` สร้างถูกทิ้งทั้งหมดตอน cron อ่านแค่คีย์เดียว
        """
        self._check_access()
        f = self._normalize_filters(filters or {})
        self = self.sudo()
        shared = self._build_shared(f)
        shared["cash_forecast"] = self._build_cash_forecast(f, shared)
        self._build_margin(f, shared)
        return {
            "filters": f["echo"],
            "forecast": self._build_forecast(f, shared),
            "updated_at": fields.Datetime.to_string(fields.Datetime.now()),
        }

    @api.model
    def get_controlling_data(self, filters=None):
        """Payload ของแท็บ Controlling อย่างเดียว — ใช้ตอนสลับ analytic plan

        การเปลี่ยนมิติศูนย์ต้นทุนไม่กระทบแท็บอื่นเลย แต่เดิมฝั่งจอเรียก
        `get_dashboard_data` ใหม่ทั้งใบ = สร้างครบ 13 แท็บเพื่อรีเฟรชตารางเดียว
        """
        self._check_access()
        f = self._normalize_filters(filters or {})
        self = self.sudo()
        shared = self._build_shared(f)
        return {
            "filters": f["echo"],
            "controlling": self._build_controlling(f, shared),
            "updated_at": fields.Datetime.to_string(fields.Datetime.now()),
        }

    @api.model
    def get_compare_data(self, filters=None):
        """Payload ของแท็บ Compare (BI) อย่างเดียว — ใช้ตอนเปลี่ยนโหมด/จำนวนงวด

        `_build_compare` ยิงคิวรีของตัวเองต่อคอลัมน์ และอ่านจาก `shared` แค่
        ผังบัญชี/ค่าตั้งค่า/mapping EBITDA ที่ `_build_shared` เตรียมไว้อยู่แล้ว
        """
        self._check_access()
        f = self._normalize_filters(filters or {})
        self = self.sudo()
        shared = self._build_shared(f)
        return {
            "filters": f["echo"],
            "compare": self._build_compare(f, shared),
            "updated_at": fields.Datetime.to_string(fields.Datetime.now()),
        }

    @api.model
    def get_channel_data(self, filters=None):
        """Payload ของแท็บ Sales Channel อย่างเดียว — โหลดตอนเปิดแท็บครั้งแรก

        แท็บนี้ **ไม่อยู่ใน `get_dashboard_data`** โดยตั้งใจ: มันคิดงบทั้งชุด
        เป็นรายเดือนทั้งปีงบ (สูงสุด 12 คอลัมน์ × 2 คิวรียอดคงเหลือ) บวกคิวรี
        แยกช่องทางอีกชุด — ไม่ควรถ่วงการโหลดหน้าแรกของทุกคนเพื่อแท็บเดียว
        `_build_channel` พึ่งแค่ผังบัญชี/mapping/ค่าตั้งค่าใน `shared`
        """
        self._check_access()
        f = self._normalize_filters(filters or {})
        self = self.sudo()
        shared = self._build_shared(f)
        return {
            "filters": f["echo"],
            "channel": self._build_channel(f, shared),
            "updated_at": fields.Datetime.to_string(fields.Datetime.now()),
        }

    @api.model
    def get_monthly_close_data(self, filters=None):
        """Payload ของหน้า Monthly Close (client action แยกจาก CFO Cockpit)

        คืนเฉพาะสไลซ์ ``close`` + ``filters`` echo + สถานะ AI — ไม่แตะเครื่องยนต์
        หนักของ 14 แท็บ  ``_build_close`` พึ่งแค่ ``shared["cfg_map"]`` จึงประกอบ
        shared แบบบางให้พอ (ดู docstring ของ _build_close)
        """
        self._check_access()
        f = self._normalize_filters(filters or {})
        self = self.sudo()
        cfg_map = self.env["biz.smart.finance.config"].get_for_companies(
            f["cids"])
        return {
            "filters": f["echo"],
            "close": self._build_close(f, {"cfg_map": cfg_map}),
            "ai": {
                "configured": self.env["biz.smart.finance.ai"].is_configured(),
                "is_manager": self.env.user.has_group(
                    "biz_smart_finance.group_bsf_manager"),
            },
            "updated_at": fields.Datetime.to_string(fields.Datetime.now()),
        }

    # ------------------------------------------------------------------
    # access / filters
    # ------------------------------------------------------------------
    def _check_access(self):
        if self.env.su:
            return
        if not self.env.user.has_group("biz_smart_finance.group_bsf_user"):
            raise AccessError(_("ต้องเป็นสมาชิกกลุ่ม CFO Cockpit / Viewer"))

    # ---- ปีงบ / งวดบัญชี (รองรับปีงบไม่ตรงปีปฏิทิน) ----
    def _fiscal_year(self, company, year):
        """ช่วงปีงบของบริษัทที่ **สิ้นสุดในปีปฏิทิน `year`**

        บริษัทที่ปิดงบ 31 ธ.ค. จะได้ 1 ม.ค.–31 ธ.ค. เท่าเดิมทุกประการ
        ถ้ามีตาราง `account.fiscal.year` (om_fiscal_year) และกรอกไว้ ให้ทับ
        ค่าที่คำนวณ — รองรับปีงบสั้น/ยาวผิดปกติโดยไม่ต้องพึ่งโมดูลนั้น
        """
        last_month = int(company.fiscalyear_last_month or 12)
        last_day = min(
            company.fiscalyear_last_day or 31,
            calendar.monthrange(year, last_month)[1],
        )
        anchor = date(year, last_month, last_day)
        if "account.fiscal.year" in self.env:
            record = self.env["account.fiscal.year"].sudo().search([
                ("company_id", "=", company.id),
                ("date_from", "<=", anchor), ("date_to", ">=", anchor),
            ], limit=1)
            if record:
                return record.date_from, record.date_to
        dates = company.compute_fiscalyear_dates(anchor)
        return dates["date_from"], dates["date_to"]

    def _fy_periods(self, fy_from, fy_to):
        """แบ่งปีงบเป็นงวดรายเดือน (P1 = เดือนแรกของปีงบ) แบบ SAP posting period

        งวดสุดท้ายถูกตัดที่วันสิ้นปีงบเสมอ จึงรองรับปีงบที่ไม่ลงตัวรายเดือน
        """
        periods, cursor, index = [], fy_from, 1
        while cursor <= fy_to:
            month_end = cursor.replace(
                day=calendar.monthrange(cursor.year, cursor.month)[1])
            end = min(month_end, fy_to)
            periods.append({
                "index": index,
                "date_from": cursor,
                "date_to": end,
                # ปีเป็น ค.ศ. เสมอ ให้ตรงกับวันที่ ISO ที่โชว์คู่กันทั้งจอ
                # (as_of, fy_label, ตารางทุกใบ) — ผสม พ.ศ./ค.ศ. อ่านแล้วสับสน
                "label": "P%d · %s %s" % (
                    index, MONTH_ABBR[cursor.month - 1], cursor.year),
            })
            cursor = end + timedelta(days=1)
            index += 1
        return periods

    def _compare_windows(self, f):
        """หน้าต่างคอลัมน์ของแท็บเปรียบเทียบ เรียงเก่า → ใหม่

        คอลัมน์ขวาสุดคืองวดที่เลือกใน toolbar เสมอ แล้วเดินถอยหลังตามโหมด
        ทุกโหมดคำนวณปีงบทีละปีจาก `_fiscal_year` (memoize) ห้าม assume ว่า
        ปีงบมี 12 งวด — om_fiscal_year ตั้งปีงบสั้น/ยาวได้

        ไม่มีคอลัมน์ไหนยื่นเกิน as_of ที่ผู้ใช้เลือก (ไตรมาสปัจจุบันที่ยัง
        ไม่ครบจะถูกตัดและติดธง partial) เพราะทั้งจอใช้กติกา "ถึงงวด" เดียวกัน
        """
        mode = f["compare_mode"]
        if not mode:
            return []
        company = f["anchor_company"]
        cache = {}

        def periods_of(year):
            if year not in cache:
                cache[year] = self._fy_periods(
                    *self._fiscal_year(company, year))
            return cache[year]

        def window(date_from, date_to, label, sub):
            end = min(date_to, f["as_of"])
            return {
                "_from": date_from,
                "_to": end,
                "label": label,
                "sub": sub + (_(" · ยังไม่ครบงวด") if end < date_to else ""),
                "date_from": str(date_from),
                "date_to": str(end),
                "as_of": str(end),
                "title": "%s – %s" % (date_from, end),
                "partial": end < date_to,
            }

        windows = []
        if mode == "month":
            year, index = f["year"], f["month"]
            for _step in range(f["compare_count"]):
                periods = periods_of(year)
                if not periods:
                    break
                index = min(max(index, 1), len(periods))
                period = periods[index - 1]
                windows.append(window(
                    period["date_from"], period["date_to"],
                    "%s %s" % (MONTH_ABBR[period["date_from"].month - 1],
                               period["date_from"].year),
                    "P%d · FY%s" % (period["index"], year),
                ))
                index -= 1
                if index < 1:
                    year -= 1
                    index = len(periods_of(year))
        elif mode == "quarter":
            year = f["year"]
            quarter = (f["month"] - 1) // 3 + 1
            for _step in range(f["compare_count"]):
                periods = periods_of(year)
                if not periods:
                    break
                # ปีงบสั้นได้ไตรมาสไม่ครบ 4 — ปัดขึ้นจากจำนวนงวดจริง
                quarters = (len(periods) + 2) // 3
                quarter = min(max(quarter, 1), quarters)
                first = periods[3 * (quarter - 1)]
                last = periods[min(3 * quarter, len(periods)) - 1]
                windows.append(window(
                    first["date_from"], last["date_to"],
                    "Q%d FY%s" % (quarter, year),
                    "P%d–P%d" % (first["index"], last["index"]),
                ))
                quarter -= 1
                if quarter < 1:
                    year -= 1
                    quarter = (len(periods_of(year)) + 2) // 3
        else:  # year — FYTD ถึงงวดลำดับเดียวกันของแต่ละปีงบ
            for offset in range(f["compare_count"]):
                year = f["year"] - offset
                periods = periods_of(year)
                if not periods:
                    break
                last = periods[min(f["month"], len(periods)) - 1]
                windows.append(window(
                    periods[0]["date_from"], last["date_to"],
                    "FY%s" % year,
                    _("ถึง P%d") % last["index"],
                ))

        windows.reverse()
        for index, col in enumerate(windows):
            col["index"] = index
            col["is_current"] = index == len(windows) - 1
        return windows

    def _presentation_currency(self, anchor_company):
        """สกุลที่ใช้แสดงผลทั้งจอ — ตั้งที่ Settings > Smart Finance

        กลุ่มที่รายงานรวมเป็นบาทต้องบังคับสกุลได้ ไม่ใช่เปลี่ยนไปตามบริษัทที่
        ผู้ใช้ล็อกอินอยู่  เว้นว่าง = ใช้สกุลของบริษัทอ้างอิงเหมือนเดิม
        ตัวเลขทุกก้อนถูกแปลงเข้าสกุลนี้ด้วยอัตราปิด ณ as_of อยู่แล้ว
        (ดู _convert) การเปลี่ยนค่านี้จึงไม่ทำให้ยอดผิดหน่วย
        """
        param = self.env["ir.config_parameter"].sudo().get_param(
            "biz_smart_finance.presentation_currency_id")
        try:
            currency = self.env["res.currency"].browse(int(param or 0)).exists()
        except (TypeError, ValueError):
            currency = self.env["res.currency"]
        return currency or anchor_company.currency_id

    def _normalize_filters(self, filters):
        today = fields.Date.context_today(self)
        allowed = self.env.user.company_ids
        company_id = filters.get("company_id") or False
        if company_id and company_id not in allowed.ids:
            company_id = False
        cids = [company_id] if company_id else allowed.ids
        # บริษัทอ้างอิงสำหรับปฏิทินปีงบ + สกุลนำเสนอ
        anchor_company = (
            self.env["res.company"].browse(company_id)
            if company_id else self.env.company
        )

        year = int(filters.get("year") or today.year)
        years = list(range(today.year - 3, today.year + 1))
        if year not in years:
            year = today.year
        scenario = filters.get("scenario") or "base"
        if scenario not in ("base", "downside", "stress"):
            scenario = "base"
        # แท็บเปรียบเทียบ (BI) — ว่าง = ปิด (ไม่ยิงคิวรีเพิ่มเลย)
        compare_mode = filters.get("compare_mode") or ""
        if compare_mode not in ("year", "quarter", "month"):
            compare_mode = ""
        try:
            compare_count = int(filters.get("compare_count") or 4)
        except (TypeError, ValueError):
            compare_count = 4
        compare_count = min(6, max(2, compare_count))
        include_sales_to_cash = filters.get("include_sales_to_cash")
        if include_sales_to_cash not in (True, False):
            include_sales_to_cash = None
        # มิติ Controlling — ตรวจว่าเป็นแผนระดับรากจริงก่อนใช้
        plan_id = int(filters.get("plan_id") or 0)
        if plan_id and plan_id not in self._controlling_plans().ids:
            plan_id = 0
        # มิติของแท็บช่องทางขาย — ค่าอื่นตกกลับเป็นค่าตั้งต้นเสมอ
        channel_dim = filters.get("channel_dim") or CHANNEL_DIM_DEFAULT
        if channel_dim not in CHANNEL_DIM_CODES:
            channel_dim = CHANNEL_DIM_DEFAULT
        # 0 = ดูรวมทุกช่องทาง; id ที่ไม่มีจริงถูกตกกลับเป็น 0 ใน _build_channel
        # (ที่นี่ยังไม่รู้ว่ามีช่องทางไหนบ้าง — ต้องอ่าน GL ก่อน)
        try:
            channel_id = int(filters.get("channel_id") or 0)
        except (TypeError, ValueError):
            channel_id = 0

        fy_start, fy_end = self._fiscal_year(anchor_company, year)
        periods = self._fy_periods(fy_start, fy_end)
        fy_start_prior, fy_end_prior = self._fiscal_year(
            anchor_company, year - 1)
        periods_prior = self._fy_periods(fy_start_prior, fy_end_prior)

        # month = ลำดับงวดในปีงบ (ปีปฏิทิน: งวด 1 = มกราคม เหมือนเดิมทุกประการ)
        month = int(filters.get("month") or 0)
        if not 1 <= month <= len(periods):
            month = next(
                (p["index"] for p in periods
                 if p["date_from"] <= today <= p["date_to"]),
                len(periods),
            )
        as_of = periods[month - 1]["date_to"]
        # งวดเดียวกันของปีงบก่อน (ไม่ใช่ −365 วัน — ปีงบสั้น/ยาวจะเพี้ยน)
        as_of_prior = periods_prior[
            min(month, len(periods_prior)) - 1]["date_to"]

        presentation = self._presentation_currency(anchor_company)
        currencies = self.env["res.company"].browse(cids).mapped("currency_id")
        # วันปิดงวดที่ผู้ใช้คนนี้แก้ย้อนหลังไม่ได้ (core คืน date.min ถ้าไม่ตั้ง)
        lock_date = anchor_company._get_user_fiscal_lock_date()
        return {
            "cids": cids,
            "presentation_currency": presentation,
            "company_id": company_id,
            # บริษัทอ้างอิงปฏิทินปีงบ — _compare_windows ต้องใช้คำนวณปีงบย้อนหลัง
            "anchor_company": anchor_company,
            "year": year,
            "month": month,
            "scenario": scenario,
            "plan_id": plan_id,
            "channel_dim": channel_dim,
            "channel_id": channel_id,
            "compare_mode": compare_mode,
            "compare_count": compare_count,
            "include_sales_to_cash": include_sales_to_cash,
            "today": today,
            "fy_start": fy_start,
            "fy_end": fy_end,
            "as_of": as_of,
            "as_of_prior": as_of_prior,
            "fy_start_prior": fy_start_prior,
            "t12m_start": as_of - timedelta(days=364),
            "echo": {
                "company_id": company_id,
                "company_label": (
                    anchor_company.name
                    if company_id else _("Group (รวมทุกบริษัท)")
                ),
                "companies": [
                    {"id": c.id, "name": c.name} for c in allowed
                ],
                "year": year,
                "years": years,
                "month": month,
                "periods": [
                    {"index": p["index"], "label": p["label"],
                     "date_from": str(p["date_from"]),
                     "date_to": str(p["date_to"])}
                    for p in periods
                ],
                "fy_label": "FY%s (%s – %s)" % (year, fy_start, fy_end),
                "fy_start": str(fy_start),
                "fy_end": str(fy_end),
                "is_calendar_fy": fy_start.month == 1 and fy_start.day == 1,
                "scenario": scenario,
                "plan_id": plan_id,
                "channel_dim": channel_dim,
                "channel_id": channel_id,
                "compare_mode": compare_mode,
                "compare_count": compare_count,
                "include_sales_to_cash": include_sales_to_cash,
                "as_of": str(as_of),
                "as_of_prior": str(as_of_prior),
                "today": str(today),
                "currency": presentation.name,
                "currency_symbol": presentation.symbol or "",
                # จริงเมื่อ "มีการแปลงสกุลเกิดขึ้น" ไม่ใช่แค่กลุ่มมีหลายสกุล —
                # บริษัทเดียวสกุล USD ที่ถูกบังคับให้นำเสนอเป็น THB ก็ต้องเตือน
                "multi_currency": (
                    len(set(currencies.ids)) > 1
                    or any(c != presentation for c in currencies)
                ),
                # งวดปิดแล้ว = ตัวเลขถือว่า final (SAP: period lock)
                "period_closed": bool(
                    lock_date and lock_date >= as_of),
                "lock_date": str(lock_date) if lock_date
                and lock_date > date.min else "",
            },
        }

    # ------------------------------------------------------------------
    # การแปลงค่าเงิน (consolidation)
    # ------------------------------------------------------------------
    def _fx_rates(self, cids, date, presentation):
        """{company_id: ตัวคูณจากสกุลของบริษัท → สกุลนำเสนอ ณ วันที่กำหนด}

        ใช้ **closing rate เดียวต่อหนึ่งคอลัมน์รายงาน** (คอลัมน์งวดนี้ใช้อัตรา
        ณ as_of, คอลัมน์งวดก่อนใช้อัตรา ณ as_of_prior) จงใจไม่ใช้ average rate
        กับ P&L เพราะการผสมสองอัตราในงบชุดเดียวจะทำให้งบดุลไม่ดุลและ identity
        ของงบกระแสเงินสดไม่ปิด ต้องมีบรรทัด CTA มาอุด — ยอมแลกความละเอียด
        กับความสอดคล้องภายในที่ตรวจสอบได้ (ดู README ข้อจำกัด)
        """
        rates = {}
        for company in self.env["res.company"].browse(cids):
            source = company.currency_id
            if not source or source == presentation:
                rates[company.id] = 1.0
                continue
            rates[company.id] = source._convert(
                1.0, presentation, company, date, round=False)
        return rates

    def _fx_rates_memo(self, shared, cids, date, presentation):
        """`_fx_rates` ที่จำผลไว้ต่อ (บริษัท, วันที่, สกุลนำเสนอ)

        `_convert` ยิง SQL หาเรตต่อบริษัทต่อการเรียกหนึ่งครั้ง และแท็บ Compare
        เรียกใหม่**ทุกคอลัมน์** (สูงสุด 6) ทั้งที่คอลัมน์เดียวกันซ้ำได้ —
        กติกา "หนึ่ง closing rate ต่อหนึ่งคอลัมน์" ไม่เสีย เพราะ key มีวันที่อยู่"""
        memo = shared.setdefault("_fx_memo", {})
        key = (frozenset(cids), date, presentation.id if presentation else 0)
        if key not in memo:
            memo[key] = self._fx_rates(cids, date, presentation)
        return memo[key]

    def _conv(self, shared, amount, company_id, prior=False):
        """แปลงยอดของบริษัทหนึ่งเป็นสกุลนำเสนอ (ไม่รู้จัก company → ไม่แปลง)"""
        rates = shared["fx_prior"] if prior else shared["fx"]
        return (amount or 0.0) * rates.get(company_id, 1.0)

    # ------------------------------------------------------------------
    # shared primitives — คิวรีหนักทั้งหมดยิงครั้งเดียวที่นี่
    # ------------------------------------------------------------------
    def _build_shared(self, f):
        cids = f["cids"]
        Config = self.env["biz.smart.finance.config"]
        cfg_map = Config.get_for_companies(cids)
        presentation = f["presentation_currency"]

        # ---- ผังบัญชีที่เกี่ยวข้อง (ครั้งเดียว) ----
        journals = self.env["account.journal"].search([
            ("type", "in", ("bank", "cash")), ("company_id", "in", cids),
        ])
        liquidity_ids = set(journals.mapped("default_account_id").ids)
        # ---- ธนาคาร (แท็บ Cash & Liquidity แยกรายธนาคาร) ----
        # journals ยังไม่ถูกทิ้ง ณ จุดนี้ — ใช้ต่อได้เลยโดยไม่ต้อง search ซ้ำ
        # liquidity_ids ด้านบนเป็น ground truth ของยอดกลุ่ม (ห้ามแก้); ชุดนี้
        # เป็นมิติเสริมสำหรับแตกรายธนาคาร ไม่ทดแทนกัน (ดู invariant ในแผน)
        banks = self.env["biz.smart.finance.bank"].search(
            [("company_id", "in", cids)])
        bank_of_journal = {
            journal.id: journal.bsf_bank_id.id
            for journal in journals if journal.bsf_bank_id
        }
        bank_journal_ids = list(bank_of_journal)
        # ยอด/สัดส่วนรายธนาคารต้องอ่านจาก account_id ของ journal (เหมือน
        # liquidity_ids ด้านบน) ห้ามใช้ journal_id คุมคิวรี AML — ผลรวม
        # "balance" ของทุกบรรทัดในสมุดรายวันเดียวกันเป็นศูนย์เสมอตามหลัก
        # double-entry (เดบิต=เครดิตภายในสมุดรายวันเดียวกันของทุกใบสำคัญ)
        # ไม่ว่าบัญชีปลายทางจะเป็นอะไร — ต้องกรองเฉพาะ "บัญชี" ของธนาคารนั้น
        bank_of_account = {
            journal.default_account_id.id: journal.bsf_bank_id.id
            for journal in journals
            if journal.bsf_bank_id and journal.default_account_id
        }
        bank_account_ids = list(bank_of_account)
        bank_rows = [{
            "id": bank.id,
            "name": bank.name,
            "company_id": bank.company_id.id,
            "min_balance": bank.min_balance,
            "is_restricted": bank.is_restricted,
            "restricted_amount": bank.restricted_amount,
            "receipt_share_pct": bank.receipt_share_pct,
            "payment_share_pct": bank.payment_share_pct,
        } for bank in banks]
        # ทั้งผังบัญชี (ไม่กรองประเภท) — งบแสดงฐานะ/กระแสเงินสดต้องเห็นทุกบัญชี
        # consumer เดิมเลือกด้วย type/id จาก map อยู่แล้ว จึงไม่กระทบ
        accounts = self.env["account.account"].search_read(
            [("company_id", "in", cids)],
            ["account_type", "company_id", "code", "name"],
        )
        acc_type = {a["id"]: a["account_type"] for a in accounts}
        acc_company = {a["id"]: a["company_id"][0] for a in accounts}
        acc_code = {a["id"]: a["code"] or "" for a in accounts}
        acc_name = {a["id"]: a["name"] or "" for a in accounts}
        # all_account_ids จำกัดที่บัญชี Odoo จริง (id บวก) เท่านั้น — ใช้กรอง
        # domain ของ account.move.line ด้านล่าง ต้องคง "ก่อน" การ inject ผัง
        # บัญชีภายนอก ไม่งั้นคิวรี AML จะมี id ติดลบปนอยู่ (ไม่ match อะไร แต่
        # ผิดหลักการ — เจตนาแยกให้ชัดว่าอันไหนคือบัญชี Odoo จริง)
        all_account_ids = list(acc_type)

        # ---- ผังบัญชีภายนอก (Trial Balance) — คีย์สังเคราะห์ติดลบ ----
        # กลไกเดียวกับ ext_partner_keys ด้านล่าง (คู่ค้าภายนอกที่ไม่ผูก
        # res.partner): inject ลง acc_type/acc_company/acc_code/acc_name แล้ว
        # ให้ยอดไหลเข้า bal_ytd/bal_cum/... ผ่าน _range_balances/_cum_balances
        # ข้างล่าง — ผลคือ BS_WATERFALL/PNL_WATERFALL/_sum_type/_build_compare
        # ใช้งานได้กับบัญชีภายนอกโดยไม่ต้องรู้ว่าที่มาคือ Odoo หรือระบบภายนอกเลย
        # (แลกมาด้วย: แถวบัญชีภายนอกไม่มีเอกสารต้นทางให้ drill ลง journal item)
        ext_accounts = self.env["biz.smart.finance.ext.account"].search_read(
            [("company_id", "in", cids)],
            ["company_id", "code", "name", "account_type",
             "is_depreciation", "is_interest", "is_tax",
             "is_debt", "is_inventory"],
        )
        dep_ids, int_ids, tax_ids = set(), set(), set()
        debt_ids, inv_ids = set(), set()
        debt_ids_by_company = defaultdict(set)
        inv_ids_by_company = defaultdict(set)
        for ext in ext_accounts:
            key = -ext["id"]
            ext_cid = ext["company_id"][0]
            acc_type[key] = ext["account_type"]
            acc_company[key] = ext_cid
            acc_code[key] = ext["code"] or ""
            acc_name[key] = ext["name"] or ""
            if ext["is_depreciation"]:
                dep_ids.add(key)
            if ext["is_interest"]:
                int_ids.add(key)
            if ext["is_tax"]:
                tax_ids.add(key)
            if ext["is_debt"]:
                debt_ids.add(key)
                debt_ids_by_company[ext_cid].add(key)
            if ext["is_inventory"]:
                inv_ids.add(key)
                inv_ids_by_company[ext_cid].add(key)
        # รวมกับ mapping บัญชี Odoo จริงของ config เดิม (M2M ไป account.account)
        # — สองแหล่งไม่ชนกันเพราะคีย์คนละเครื่องหมาย
        for cfg in cfg_map.values():
            cfg_cid = cfg.company_id.id
            dep_ids |= set(cfg.depreciation_account_ids.ids)
            int_ids |= set(cfg.interest_account_ids.ids)
            tax_ids |= set(cfg.tax_account_ids.ids)
            if cfg.debt_account_ids:
                cfg_debt = set(cfg.debt_account_ids.ids)
                debt_ids |= cfg_debt
                debt_ids_by_company[cfg_cid] |= cfg_debt
            if cfg.inventory_account_ids:
                cfg_inv = set(cfg.inventory_account_ids.ids)
                inv_ids |= cfg_inv
                inv_ids_by_company[cfg_cid] |= cfg_inv

        # mapping บัญชีของงบแสดงฐานะการเงิน (Odoo account เท่านั้น) — บรรทัด
        # "อื่น ๆ" ของแต่ละ type = ยอดที่เหลือหลังหักบัญชีที่ map ทุกช่อง
        bs_map_ids = {"inventory": set(inv_ids)}
        for key, field_name in BS_MAP_FIELDS.items():
            ids = set()
            for cfg in cfg_map.values():
                ids |= set(cfg[field_name].ids)
            bs_map_ids[key] = ids
        # เงินปันผลจ่ายเก็บแยก — **ไม่รวมใน bs_all_mapped** เพราะบัญชีเจ้าหนี้
        # เงินปันผลยังต้องอยู่ในบรรทัดหนี้สินหมุนเวียนของงบดุลตามปกติ
        cf_dividend_ids = set()
        for cfg in cfg_map.values():
            cf_dividend_ids |= set(cfg.cf_dividend_account_ids.ids)

        # ชื่อบริษัทใช้ซ้ำหลายแท็บ — อ่านครั้งเดียวแทนการ browse ทีละ id ในลูป
        company_name = {
            company.id: company.name
            for company in self.env["res.company"].browse(cids)
        }

        # ---- อัตราแลกเปลี่ยนสองชุด — คอลัมน์งวดนี้ / คอลัมน์งวดก่อน ----
        fx_now = self._fx_rates(cids, f["as_of"], presentation)
        fx_prior = self._fx_rates(cids, f["as_of_prior"], presentation)

        # ------------------------------------------------------------
        # แหล่งข้อมูล GL รายเดือน (Monthly Close Cockpit) — ทะเบียนงวดที่
        # override ไว้เท่านั้น (ไม่มีแถว = ใช้ค่าตั้งต้นบริษัทจาก cfg.gl_source
        # เหมือนเดิมทุกประการ = "fast path" ที่ไม่ยิงคิวรีเพิ่มแม้แต่ครั้งเดียว)
        # ------------------------------------------------------------
        default_gl_source = {
            cid: self._cfg_source(cfg_map, cid, "gl_source") for cid in cids
        }
        period_rows = self.env["biz.smart.finance.period"].search_read(
            [("company_id", "in", cids), ("gl_source", "not in", (False, ""))],
            ["company_id", "date_from", "date_to", "gl_source"],
            order="date_from",
        ) if cids else []
        gl_cells_by_company = defaultdict(list)
        for row in period_rows:
            gl_cells_by_company[row["company_id"][0]].append(
                (row["date_from"], row["date_to"], row["gl_source"]))
        has_ext_gl = (
            any(v == "external" for v in default_gl_source.values())
            or any(row["gl_source"] == "external" for row in period_rows)
        )

        def gl_source_at(company_id, day):
            for d_from, d_to, source in gl_cells_by_company.get(
                    company_id, ()):
                if d_from <= day <= d_to:
                    return source
            return default_gl_source.get(company_id, "odoo")

        def month_bounds(day):
            start = day.replace(day=1)
            next_month = date(
                start.year + (start.month == 12),
                (start.month % 12) + 1, 1)
            return start, next_month - timedelta(days=1)

        def aml_range(company_ids, date_from, date_to, rates):
            """{account_key: balance} จาก account.move.line ล้วน ๆ (posted,
            แปลงสกุลแล้ว) — เดิม balances() ก่อนมีแหล่งภายนอก ยังเป็นคิวรี
            เดียวเมื่อไม่มี company ไหน override เป็น external เลย"""
            if not company_ids:
                return {}
            domain = [
                ("parent_state", "=", "posted"),
                ("company_id", "in", company_ids),
                ("account_id", "in", all_account_ids),
                ("date", "<=", str(date_to)),
            ]
            if date_from:
                domain.append(("date", ">=", str(date_from)))
            rows = self.env["account.move.line"]._read_group(
                domain, groupby=["account_id"], aggregates=["balance:sum"],
            )
            return {
                acc.id: (bal or 0.0) * rates.get(acc_company.get(acc.id), 1.0)
                for acc, bal in rows
            }

        def ext_cells_in_range(date_from, date_to):
            """[(company_id, month_start, month_end)] เดือนปฏิทินที่เป็น
            external และคาบเกี่ยว [date_from, date_to] — ใช้เฉพาะช่วงมีขอบเขต
            (bal_ytd/bal_t12m ฯลฯ) จึงวนเป็นเดือนได้โดยไม่แพง"""
            cells = []
            for cid in company_ids_with_ext(cids):
                cursor, _ = month_bounds(date_from)
                while cursor <= date_to:
                    c_start, c_end = month_bounds(cursor)
                    if gl_source_at(cid, c_start) == "external":
                        cells.append((cid, c_start, c_end))
                    cursor = c_end + timedelta(days=1)
            return cells

        def company_ids_with_ext(company_ids):
            return [
                cid for cid in company_ids
                if default_gl_source.get(cid) == "external"
                or cid in gl_cells_by_company
            ]

        def ext_gl_movement(cells, rates):
            """{account_key: movement} จาก ext.gl.line ของแต่ละ (company,
            เดือน) ที่ระบุ — ใช้ยอด debit-credit ของงวดนั้นตรง ๆ (movement)
            เดือนที่ยังไม่มี TB ยืนยัน (posted) ถือว่าไม่มีข้อมูล = 0

            ยิงคิวรีเดียวสำหรับทุกช่อง (เดิมเป็นหนึ่งคิวรีต่อ บริษัท×เดือน
            = หลักร้อยคิวรีต่อการโหลดหนึ่งครั้ง) — Counter รักษาพฤติกรรมเดิม
            ไว้เป๊ะเผื่อผู้เรียกส่งช่องซ้ำเข้ามา (เดิมจะบวกซ้ำตามจำนวนครั้ง)"""
            if not cells:
                return {}
            cell_count = Counter((cid, m_end) for cid, _start, m_end in cells)
            lines = self.env["biz.smart.finance.ext.gl.line"].search_read(
                [("company_id", "in", list({c for c, _ in cell_count})),
                 ("date_to", "in", sorted({d for _, d in cell_count})),
                 ("state", "=", "posted")],
                ["company_id", "date_to", "ext_account_id", "balance"],
            )
            result = defaultdict(float)
            for line in lines:
                cid = line["company_id"][0]
                times = cell_count.get((cid, line["date_to"]), 0)
                if not times:
                    continue
                result[-line["ext_account_id"][0]] += (
                    (line["balance"] or 0.0) * rates.get(cid, 1.0) * times)
            return dict(result)

        def ext_strip_batch(date_from, date_to, cells, rates):
            """ยอด AML ที่ต้องหักออกของ **ทุกช่อง external พร้อมกัน**

            เทียบเท่ากับการเรียก aml_range ต่อช่องแบบเดิมทุกประการ: โดเมนถูก
            clamp ด้วย [date_from, date_to] อยู่แล้ว การ groupby รายเดือนจึง
            ให้ผลเท่ากับ max(date_from, m_start) / min(date_to, m_end) ของเดิม
            (เดือนหัว-ท้ายที่ขอบตกกลางเดือนถูกตัดโดยโดเมน ไม่ใช่โดยการจัดกลุ่ม)
            อัตราแลกเปลี่ยนยังอิง **บริษัทของบัญชี** เหมือน aml_range"""
            if not cells:
                return {}
            cell_keys = {(cid, m_start) for cid, m_start, _end in cells}
            rows = self.env["account.move.line"]._read_group(
                [("parent_state", "=", "posted"),
                 ("company_id", "in", list({cid for cid, _s, _e in cells})),
                 ("account_id", "in", all_account_ids),
                 ("date", ">=", str(date_from)),
                 ("date", "<=", str(date_to))],
                groupby=["company_id", "account_id", "date:month"],
                aggregates=["balance:sum"],
            )
            strip = defaultdict(float)
            for company, acc, month, bal in rows:
                if (company.id, month) not in cell_keys:
                    continue
                strip[acc.id] += (bal or 0.0) * rates.get(
                    acc_company.get(acc.id), 1.0)
            return strip

        def range_balances(date_from, date_to, rates):
            """movement รวมของช่วง [date_from, date_to] ต่อบัญชี — ตัดสลับ
            Odoo/ภายนอกได้เป็นรายเดือน กติกา: 'strip' (ตัด AML ออก) ตัดเฉพาะ
            ส่วนที่คาบเกี่ยวช่วงจริง ๆ (แม่นยำ) ส่วน 'add' (เติมยอดภายนอก) เติม
            ทั้งเดือนเสมอที่เดือนนั้นคาบเกี่ยว (ประมาณเมื่อขอบช่วงตกกลางเดือน
            ภายนอก — เกิดเฉพาะ bal_t12m ที่ t12m_start ไม่ใช่วันต้นเดือนเสมอไป
            บัญชีสะสม/YTD ใช้ขอบงวดที่เป็นวันสิ้นเดือนอยู่แล้วจึงไม่กระทบ)"""
            base = aml_range(cids, date_from, date_to, rates)
            if not has_ext_gl:
                return base
            cells = ext_cells_in_range(date_from, date_to)
            if not cells:
                return base
            for key, value in ext_strip_batch(
                    date_from, date_to, cells, rates).items():
                base[key] = base.get(key, 0.0) - value
            for key, value in ext_gl_movement(cells, rates).items():
                base[key] = base.get(key, 0.0) + value
            return base

        def tb_closing_batch(pairs, rates):
            """{company_id: {account_key: closing}} ของงวด TB ล่าสุดที่
            date_to <= day ของแต่ละบริษัท — closing ของ TB สะสมประวัติทั้งหมด
            ของตัวเองไว้แล้ว จึงใช้แทนยอดสะสม Odoo ได้ตรง ๆ ไม่ต้องยิงคิวรี AML
            ย้อนไปไกลแค่ไหนก็ได้ ยังไม่มี TB ยืนยันก่อนวันนั้นเลย = ยอดว่าง
            (ไปขึ้น empty_hints)

            pairs = [(company_id, day)] — ยิงหนึ่งคิวรีต่อ "วัน" ที่ไม่ซ้ำกัน
            (ปกติ 1-2 วัน) แทนหนึ่งคิวรีต่อบริษัท แล้วอ่านบรรทัดทุกงวดรวดเดียว"""
            if not pairs:
                return {}
            by_day = defaultdict(list)
            for cid, day in pairs:
                by_day[day].append(cid)
            gl_of_company = {}
            for day, day_cids in by_day.items():
                # เรียงจากเก่าไปใหม่ แล้วให้ตัวหลังทับ = งวดล่าสุดต่อบริษัทชนะ
                for row in self.env["biz.smart.finance.ext.gl"].search_read(
                        [("company_id", "in", day_cids),
                         ("state", "=", "posted"),
                         ("date_to", "<=", str(day))],
                        ["company_id"], order="date_to"):
                    gl_of_company[row["company_id"][0]] = row["id"]
            if not gl_of_company:
                return {}
            company_of_gl = {v: k for k, v in gl_of_company.items()}
            result = defaultdict(dict)
            for line in self.env["biz.smart.finance.ext.gl.line"].search_read(
                    [("gl_id", "in", list(company_of_gl))],
                    ["gl_id", "ext_account_id", "closing"]):
                cid = company_of_gl[line["gl_id"][0]]
                result[cid][-line["ext_account_id"][0]] = (
                    (line["closing"] or 0.0) * rates.get(cid, 1.0))
            return result

        def last_cutover_to_odoo(cid, upto):
            """วันแรกที่บริษัทนี้ 'กลับมา' เป็น Odoo อย่างต่อเนื่องจนถึง upto
            — สมมติฐาน: สลับแหล่งครั้งเดียวต่อบริษัท (ตัดจากระบบเดิมมา Odoo
            ครั้งเดียว ไม่ใช่สลับไปมาหลายรอบ) None = ไม่มีประวัติภายนอกก่อน
            upto เลย (ให้ผู้เรียกอ่านแบบ Odoo ล้วนตามปกติ)"""
            cells = gl_cells_by_company.get(cid, ())
            ext_ends = [d_to for d_from, d_to, src in cells
                        if src == "external" and d_to < upto]
            if ext_ends:
                return max(ext_ends) + timedelta(days=1)
            if default_gl_source.get(cid) == "external":
                odoo_starts = [
                    d_from for d_from, d_to, src in cells
                    if src == "odoo" and d_from <= upto <= d_to
                ]
                if odoo_starts:
                    return min(odoo_starts)
            return None

        def cum_balances(date_to, rates):
            """ยอดสะสมถึง date_to ต่อบัญชี — **ไม่ใช่** สูตรเดียวกับ
            range_balances เพราะ 'closing' ของ TB ภายนอกเป็นยอดสะสมอยู่แล้ว
            บวกซ้อนกับ movement ของ Odoo ตรง ๆ ไม่ได้ (นับซ้ำช่วงก่อน cutover)
            — บริษัทที่ปัจจุบัน(ณ date_to)เป็น odoo แต่มีประวัติภายนอกอยู่ก่อน
            หน้า จะได้ 'ยอดยกมา ณ จุดตัด (จาก TB) + movement ของ Odoo ตั้งแต่
            จุดตัด' แทนการอ่าน AML ทั้งประวัติ"""
            if not has_ext_gl:
                return aml_range(cids, None, date_to, rates)
            # รอบแรกแค่ "จัดประเภทบริษัท" ไม่ยิงคิวรีเลย แล้วค่อยยิงเป็นชุด
            # ตามประเภท — เดิมยิง TB หนึ่งคิวรีต่อบริษัท (×4 การเรียก)
            plain, tb_pairs, cutovers = [], [], []
            for cid in cids:
                if (default_gl_source.get(cid) != "external"
                        and cid not in gl_cells_by_company):
                    plain.append(cid)
                    continue
                if gl_source_at(cid, date_to) == "external":
                    tb_pairs.append((cid, date_to))
                    continue
                cut = last_cutover_to_odoo(cid, date_to)
                if cut is None:
                    plain.append(cid)
                    continue
                cutovers.append((cid, cut))
                tb_pairs.append((cid, cut - timedelta(days=1)))
            tb_closing = tb_closing_batch(tb_pairs, rates)
            result = {}
            for cid, _day in tb_pairs:
                result.update(tb_closing.get(cid, {}))
            # บริษัทที่ตัดมา Odoo วันเดียวกันรวมเป็นคิวรีเดียว (ปกติทั้งกลุ่ม
            # ตัดพร้อมกันอยู่แล้ว) — ยอดยกมาจาก TB ด้านบนถูกเติมไปแล้ว
            by_cut = defaultdict(list)
            for cid, cut in cutovers:
                by_cut[cut].append(cid)
            for cut, cut_cids in by_cut.items():
                for key, value in aml_range(
                        cut_cids, cut, date_to, rates).items():
                    result[key] = result.get(key, 0.0) + value
            if plain:
                result.update(aml_range(plain, None, date_to, rates))
            return result

        bal_ytd = range_balances(f["fy_start"], f["as_of"], fx_now)
        bal_prior_ytd = range_balances(
            f["fy_start_prior"], f["as_of_prior"], fx_prior)
        bal_t12m = range_balances(f["t12m_start"], f["as_of"], fx_now)
        bal_cum = cum_balances(f["as_of"], fx_now)
        bal_cum_prior = cum_balances(f["as_of_prior"], fx_prior)
        # ยอดยกมาก่อนต้นงวด — ใช้เป็นฐาน Δ ของงบกระแสเงินสดทางอ้อม
        # (ใช้อัตราเดียวกับ bal_cum เพื่อให้ Δ เป็นการเคลื่อนไหวล้วน ไม่ปน FX)
        bal_open = cum_balances(f["fy_start"] - timedelta(days=1), fx_now)
        bal_open_prior = cum_balances(
            f["fy_start_prior"] - timedelta(days=1), fx_prior)

        # ---- ลูกหนี้/เจ้าหนี้คงค้าง (รายบรรทัด — bucket ใน Python) ----
        # บริษัทที่ตั้ง invoice_source = external ไม่อ่าน GL เลย เอกสารมาจาก
        # ตาราง External Invoices แทน แล้วผสมเป็นลิสต์เดียว — ทุกแท็บที่อ่าน
        # ar_items/ap_items (AR aging, AP plan, cash forecast, sales) จึงได้
        # ตัวเลขชุดเดียวกันโดยไม่ต้องรู้ว่าข้อมูลมาจากไหน
        inv_ext_cids = [
            cid for cid in cids
            if self._cfg_source(cfg_map, cid, "invoice_source") == "external"
        ]
        inv_odoo_cids = [cid for cid in cids if cid not in inv_ext_cids]

        def open_items(account_type, sign=1):
            if not inv_odoo_cids:
                return []
            # ผังบัญชีอ่านไปแล้วด้านบน — ระบุ id ตรง ๆ แทน dotted path ที่
            # กลายเป็น subselect บน account_account ทุกครั้งที่ยิงคิวรีนี้
            type_account_ids = [
                aid for aid, atype in acc_type.items()
                if atype == account_type and aid > 0
                and acc_company.get(aid) in inv_odoo_cids
            ]
            if not type_account_ids:
                return []
            rows = self.env["account.move.line"].search_read(
                [
                    ("account_id", "in", type_account_ids),
                    ("parent_state", "=", "posted"),
                    ("reconciled", "=", False),
                    ("amount_residual", "!=", 0),
                    ("company_id", "in", inv_odoo_cids),
                ],
                ["amount_residual", "date_maturity", "date",
                 "partner_id", "company_id", "move_id"],
            )
            return [
                dict(item, amount_residual=sign * item["amount_residual"]
                     * fx_now.get(item["company_id"][0], 1.0))
                for item in rows
            ]

        # คู่ค้าภายนอกที่ไม่ได้ผูก res.partner ได้คีย์ "ลบ" ประจำชื่อ — จัดกลุ่ม
        # ตามชื่อได้จริงโดยไม่ชนกับ partner id (บวก) และไม่ยุบเป็น "ไม่ระบุ" (0)
        ext_partner_keys = {}

        def ext_items(doc_type):
            if not inv_ext_cids:
                return []
            rows = self.env["biz.smart.finance.ext.invoice"].search_read(
                [
                    ("company_id", "in", inv_ext_cids),
                    ("doc_type", "=", doc_type),
                    ("amount_residual", "!=", 0),
                    ("date", "<=", str(f["as_of"])),
                ],
                ["amount_residual", "date", "date_due", "partner_id",
                 "partner_name", "company_id", "number"],
            )
            items = []
            for row in rows:
                partner = row["partner_id"]
                if not partner:
                    name = row["partner_name"] or _("ไม่ระบุ")
                    if name not in ext_partner_keys:
                        ext_partner_keys[name] = -(len(ext_partner_keys) + 1)
                    partner = (ext_partner_keys[name], name)
                items.append({
                    # ยอดภายนอกเป็นบวกทั้งสองฝั่ง — ไม่ต้องกลับเครื่องหมายแบบ GL
                    "amount_residual": (row["amount_residual"] or 0.0)
                    * fx_now.get(row["company_id"][0], 1.0),
                    "date": row["date"],
                    "date_maturity": row["date_due"] or row["date"],
                    "partner_id": partner,
                    "company_id": row["company_id"],
                    "move_id": False,
                    "external": True,
                    "number": row["number"],
                })
            return items

        ar_items = open_items(AR_TYPE) + ext_items("ar")
        ap_items = open_items(AP_TYPE, sign=-1) + ext_items("ap")

        # backlog ต่อบริษัท — ใช้ทั้งตาราง BU (Overview) และ funnel (Sales)
        backlog_rows = self.env["sale.order.line"]._read_group(
            [
                ("state", "=", "sale"),
                ("company_id", "in", cids),
                ("display_type", "=", False),
            ],
            groupby=["company_id"],
            aggregates=["untaxed_amount_to_invoice:sum"],
        )
        backlog_by_company = {
            c.id: (v or 0.0) * fx_now.get(c.id, 1.0) for c, v in backlog_rows
        }

        # project → company: แหล่งข้อมูลฝั่งโครงการหลายตัว (แผนวางบิล/แผนจ่าย/
        # retention) ไม่มี company_id ให้อ่านตรง ๆ ต้องย้อนผ่านโครงการเพื่อ
        # หาอัตราแลกเปลี่ยนที่ถูกตัว
        project_company = {
            p["id"]: (p["company_id"][0] if p["company_id"] else False)
            for p in self.env["project.project"].search_read(
                [("company_id", "in", cids)], ["company_id"])
        }

        shared = {
            "project_company": project_company,
            "backlog_by_company": backlog_by_company,
            "fx": fx_now,
            "fx_prior": fx_prior,
            "presentation": presentation,
            "cfg_map": cfg_map,
            "company_name": company_name,
            "acc_type": acc_type,
            "acc_company": acc_company,
            "acc_code": acc_code,
            "acc_name": acc_name,
            "liquidity_ids": liquidity_ids,
            "bank_rows": bank_rows,
            "bank_of_journal": bank_of_journal,
            "bank_journal_ids": bank_journal_ids,
            "bank_of_account": bank_of_account,
            "bank_account_ids": bank_account_ids,
            "bal_ytd": bal_ytd,
            "bal_prior_ytd": bal_prior_ytd,
            "bal_t12m": bal_t12m,
            "bal_cum": bal_cum,
            "bal_cum_prior": bal_cum_prior,
            "bal_open": bal_open,
            "bal_open_prior": bal_open_prior,
            "ar_items": ar_items,
            "ap_items": ap_items,
            "inv_ext_cids": inv_ext_cids,
            "inv_odoo_cids": inv_odoo_cids,
            "weeks": self._week_grid(f["today"]),
            # mapping บัญชี (Odoo M2M ∪ ธงบัญชีภายนอก) — ดูหมายเหตุด้านบน
            "dep_ids": dep_ids,
            "int_ids": int_ids,
            "tax_ids": tax_ids,
            "debt_ids": debt_ids,
            "debt_ids_by_company": dict(debt_ids_by_company),
            "inv_ids": inv_ids,
            "inv_ids_by_company": dict(inv_ids_by_company),
            "bs_map_ids": bs_map_ids,
            "cf_dividend_ids": cf_dividend_ids,
            "ebitda_configured": bool(int_ids or tax_ids),
            "has_ext_gl": has_ext_gl,
            "default_gl_source": default_gl_source,
        }
        shared["pl_ytd"] = self._pl_from_balances(shared, cfg_map, "bal_ytd")
        shared["pl_prior"] = self._pl_from_balances(shared, cfg_map, "bal_prior_ytd")
        shared["pl_t12m"] = self._pl_from_balances(shared, cfg_map, "bal_t12m")
        shared["scenario_fx"] = self._scenario_multipliers(f, cfg_map)
        shared["min_cash"] = sum(
            self._conv(shared, cfg.min_cash_requirement, cfg.company_id.id)
            for cfg in cfg_map.values()
        )
        return shared

    def _week_grid(self, today):
        monday = today - timedelta(days=today.weekday())
        weeks = []
        for index in range(WEEK_COUNT):
            wf = monday + timedelta(weeks=index)
            wt = wf + timedelta(days=6)
            weeks.append({
                "index": index,
                "label": "W%s" % wf.isocalendar()[1],
                "sub": "%02d/%02d" % (wf.day, wf.month),
                "date_from": str(wf),
                "date_to": str(wt),
                "_from": wf,
                "_to": wt,
                "is_actual": index == 0,
            })
        return weeks

    def _week_index(self, weeks, day):
        """สัปดาห์ของวันที่ (เกินขอบล่าง → 0, เกินขอบบน → None = พ้น horizon)

        กริดเป็นสัปดาห์ติดกันเริ่มวันจันทร์เสมอ (`_week_grid`) จึงคำนวณตรง ๆ
        ได้ — เดิมสแกนลิสต์ 13 ช่องต่อการเรียกหนึ่งครั้ง และถูกเรียกต่อรายการ
        AR/AP/PO/plan line ทั้งใน `_build_cash_forecast` และซ้ำอีกใน `_build_ap`
        """
        if not day:
            return 0
        first = weeks[0]
        if day <= first["_to"]:
            return 0
        index = (day - first["_from"]).days // 7
        return index if index < len(weeks) else None

    def _pl_from_balances(self, shared, cfg_map, key):
        """งบกำไรขาดทุนจาก balance ต่อบัญชี — รวมทุกบริษัทและแยกต่อบริษัท"""
        acc_type = shared["acc_type"]
        acc_company = shared["acc_company"]
        # เซ็ตพร้อมใช้จาก _build_shared แล้ว (Odoo M2M ∪ ธงบัญชีภายนอก)
        dep_ids = shared["dep_ids"]
        int_ids = shared["int_ids"]
        tax_ids = shared["tax_ids"]

        by_company = defaultdict(lambda: {
            "revenue": 0.0, "revenue_op": 0.0, "other_income": 0.0,
            "cogs": 0.0, "opex": 0.0,
            "depreciation": 0.0, "interest": 0.0, "tax": 0.0,
        })
        for account_id, balance in shared[key].items():
            atype = acc_type.get(account_id)
            bucket = by_company[acc_company.get(account_id)]
            if atype in REVENUE_TYPES:
                bucket["revenue"] -= balance
                # แยกรายได้จากการดำเนินงาน (income) กับรายได้อื่น (income_other)
                # เพื่อวางงบ waterfall — รวมกันยังเท่า revenue เดิมเสมอ
                if atype == "income_other":
                    bucket["other_income"] -= balance
                else:
                    bucket["revenue_op"] -= balance
            elif atype in COGS_TYPES:
                bucket["cogs"] += balance
            elif atype in OPEX_TYPES:
                bucket["opex"] += balance
                if atype == "expense_depreciation":
                    bucket["depreciation"] += balance
            # บัญชีที่ map ไว้ (ค่าเสื่อมนอกประเภท / ดอกเบี้ย / ภาษี) — บวกกลับ EBITDA
            if account_id in dep_ids and atype != "expense_depreciation":
                bucket["depreciation"] += balance
            if account_id in int_ids:
                bucket["interest"] += balance
            if account_id in tax_ids:
                bucket["tax"] += balance
        for bucket in by_company.values():
            bucket["gross"] = bucket["revenue"] - bucket["cogs"]
            bucket["net"] = bucket["revenue"] - bucket["cogs"] - bucket["opex"]
            bucket["ebitda"] = (
                bucket["net"] + bucket["depreciation"]
                + bucket["interest"] + bucket["tax"]
            )
            # ชั้นของงบ waterfall — sga เป็นตัวปิด (opex ที่เหลือหลังหักค่าเสื่อม/
            # ดอกเบี้ย/ภาษีที่กระจายอยู่ในหลายบัญชี) จึงกระทบยอดถึง net เสมอ
            bucket["gross_op"] = bucket["revenue_op"] - bucket["cogs"]
            bucket["sga"] = (
                bucket["opex"] - bucket["depreciation"]
                - bucket["interest"] - bucket["tax"]
            )
            bucket["ebit"] = bucket["ebitda"] - bucket["depreciation"]
            bucket["pretax"] = bucket["ebit"] - bucket["interest"]
        total = {
            k: sum(b[k] for b in by_company.values())
            for k in ("revenue", "revenue_op", "other_income", "cogs", "opex",
                      "depreciation", "interest", "tax", "gross", "net",
                      "ebitda", "gross_op", "sga", "ebit", "pretax")
        }
        return {"total": total, "by_company": dict(by_company)}

    def _scenario_multipliers(self, f, cfg_map):
        configs = list(cfg_map.values())

        def avg(field, default):
            values = [cfg[field] for cfg in configs if cfg[field]]
            return sum(values) / len(values) if values else default

        if f["scenario"] == "downside":
            return {
                "collection_delay_pct": round(
                    avg("downside_collection_delay_pct", 20.0), 1),
                "margin_hit_pct": round(avg("downside_margin_hit_pct", 2.0), 1),
            }
        if f["scenario"] == "stress":
            return {
                "collection_delay_pct": round(
                    avg("stress_collection_delay_pct", 40.0), 1),
                "margin_hit_pct": round(avg("stress_margin_hit_pct", 5.0), 1),
            }
        return {"collection_delay_pct": 0.0, "margin_hit_pct": 0.0}

    # ------------------------------------------------------------------
    # แหล่งเงินเข้า-ออกที่ยัง "ไม่เป็นเอกสารบัญชี" — ใช้ร่วมกริดสัปดาห์/เดือน
    # ------------------------------------------------------------------
    def _sales_to_cash_bill_date(self, partner, delivery_date):
        """Return the first billing date on/after delivery without inventing a
        date when customer master data is incomplete."""
        if not delivery_date:
            return None
        if partner.bsf_billing_mode == "delivery":
            return delivery_date
        # แต่ละ token แยกอิสระ — token เดียวพัง (เช่น comma ท้ายสตริง "10,25,")
        # ต้องไม่ทิ้งวันที่ token อื่นที่ parse สำเร็จไปด้วย
        days = set()
        for token in (partner.bsf_billing_days or "").split(","):
            token = token.strip()
            if not token:
                continue
            try:
                value = int(token)
            except ValueError:
                continue
            if 1 <= value <= 31:
                days.add(value)
        days = sorted(days)
        if not days:
            return None
        cursor = delivery_date.replace(day=1)
        for _index in range(13):
            last = calendar.monthrange(cursor.year, cursor.month)[1]
            for day in days:
                candidate = cursor.replace(day=min(day, last))
                if candidate >= delivery_date:
                    return candidate
            cursor += relativedelta(months=1)
        return None

    def _sales_to_cash_due_date(self, order, bill_date):
        """Use the term engine when available.  The fallback is intentionally
        conservative: a missing/unsupported term is a review exception, not a
        same-day collection assumption."""
        if not bill_date or not order.payment_term_id:
            return None
        term = order.payment_term_id
        try:
            # The term engine needs amounts to resolve percent/balance lines.
            # One currency unit is enough because we only need the resulting
            # date(s), while still preserving fixed-day and month-end rules.
            terms = term._compute_terms(
                date_ref=bill_date, currency=order.currency_id,
                company=order.company_id, tax_amount=0.0,
                tax_amount_currency=0.0, sign=1,
                untaxed_amount=1.0, untaxed_amount_currency=1.0,
            )
            dates = [entry["date"] for entry in terms.get("line_ids", []) if entry.get("date")]
            return max(dates) if dates else None
        except (AttributeError, TypeError, KeyError, ValueError):
            # An unknown term implementation must be reviewed rather than
            # silently treated as immediate payment.
            pass
        return None

    def _forecast_sources(self, f, shared):
        """คิวรีแหล่งข้อมูลนอกงบ (แผนวางบิล/แผนจ่าย/เงินประกัน/PO) ครั้งเดียว

        กริด 13 สัปดาห์ (Cash) กับกริดรายเดือน (Forecast) ต้องเห็นตัวเลข
        **ชุดเดียวกัน** ไม่งั้นสองแท็บบนจอเดียวจะขัดกันเอง — คิวรีจึงอยู่ที่นี่
        ที่เดียว แปลงสกุลแล้ว พร้อมกติกากันนับซ้ำกับเอกสารจริง (ดู docstring
        ของ `_build_forecast` สำหรับตารางกันนับซ้ำทั้งชุด)
        """
        if "fc_sources" in shared:
            return shared["fc_sources"]
        cids = f["cids"]
        project_company = shared["project_company"]
        conv = lambda amount, project_id: self._conv(
            shared, amount, project_company.get(project_id))

        # แผนวางบิลลูกค้า (เฉพาะยอดที่ยังไม่วางบิล — ยอดที่วางบิลแล้วมีตัวตน
        # เป็นลูกหนี้ในระบบบัญชีอยู่แล้ว การนับซ้ำคือบั๊กเบอร์หนึ่งของจอนี้)
        #
        # ตั้งแต่ใบตั้งเบิกผูกงวดเอง (``ai.pm.progress.claim.payment_plan_line_id``)
        # ทุกงวดถือ ``billed_amount`` ของตัวเองจริง จึงหักเป็น "รายงวด" ได้ตรง ๆ
        # เดิมที่นี่ต้องหักยอดระดับ *โครงการ* แล้วกระจายลงงวดตามวันวางบิลเร็ว→ช้า
        # เพราะกติกา claim carrier เก่าฉายยอดทั้งโครงการรวมลงงวดแรกงวดเดียว
        # (งวด 2..N จึงมี billed_amount = 0 ถาวรแม้วางบิลไปแล้ว) — วิธีเดิมให้
        # *ผลรวม* ถูกแต่ลง *งวดผิด* เมื่องวดผูกใบตั้งเบิกจริงแล้ว
        #
        # ยอดคงเหลือของงวด clamp ที่ 0: ใบตั้งเบิกที่ QS อนุมัติเกินยอดงวดตามแผน
        # ต้องไม่ทำให้งวดนั้นกลายเป็นเงินเข้าติดลบ
        plan_rows = []
        for line in self.env["ai.pm.payment.plan.line"].search_read(
            [("plan_id.project_id.company_id", "in", cids)],
            ["amount", "billed_amount", "bill_date", "project_id"],
        ):
            if not line["bill_date"]:
                continue
            amount = (line["amount"] or 0.0) - (line["billed_amount"] or 0.0)
            if amount <= 0.0:
                continue
            project = line["project_id"]
            project_id = project[0] if project else 0
            plan_rows.append({
                "project_id": project_id,
                "date": line["bill_date"],
                "amount": conv(amount, project_id),
            })

        # แผนจ่ายผู้รับเหมา (เฉพาะงวดที่ยังไม่มี vendor bill — ใบที่ตั้งแล้ว
        # กลายเป็น AP คงค้างไปแล้ว)  ใช้วันเดียวกับที่ระบบแจ้งผู้รับเหมาไว้
        # (ช้าสุดระหว่างรอบเงินลูกค้ากับเครดิตเทอมของเรา + วันเผื่อ) ไม่ใช่
        # due_date ดิบ — ไม่งั้นจอนี้กับแอปผู้รับเหมาจะบอกวันเงินออกคนละวัน
        vendor_rows = []
        for line in self.env["ai.pm.vendor.payment.line"].search_read(
            [("project_id.company_id", "in", cids)],
            ["residual_amount", "due_date", "expected_pay_date", "bill_ids",
             "project_id"],
        ):
            if line["bill_ids"] or (line["residual_amount"] or 0.0) <= 0:
                continue
            project = line["project_id"]
            project_id = project[0] if project else 0
            vendor_rows.append({
                "project_id": project_id,
                "date": line["expected_pay_date"] or line["due_date"],
                "amount": conv(line["residual_amount"], project_id),
            })

        # แผนคืนเงินประกัน — schedule ไม่มียอด ต้อง derive จากยอดที่ถือคงเหลือ
        retention_residual = {}
        rows = self.env["ai.pm.retention.line"]._read_group(
            [("project_id.company_id", "in", cids)],
            groupby=["project_id", "side"],
            aggregates=["residual_amount:sum"],
        )
        for project, side, residual in rows:
            retention_residual[(project.id, side)] = residual or 0.0
        retention_rows = []
        for line in self.env["ai.pm.retention.schedule.line"].search_read(
            [
                ("project_id.company_id", "in", cids),
                ("state", "=", "planned"),
                ("date_due", "!=", False),
            ],
            ["project_id", "side", "percent_of_held", "date_due"],
        ):
            project_id = line["project_id"][0]
            held = retention_residual.get((project_id, line["side"]), 0.0)
            retention_rows.append({
                "project_id": project_id,
                "side": line["side"],
                "date": line["date_due"],
                "amount": conv(
                    held * (line["percent_of_held"] or 0.0) / 100.0, project_id),
            })

        # PO วัสดุที่ยืนยันแล้วแต่ยังไม่ตั้งบิล (ส่วนที่ตั้งบิลแล้วเป็น AP ไปแล้ว
        # และ PO งานจ้างผู้รับเหมามีแผนจ่ายของตัวเองข้างบน)
        po_open = []
        for line in self.env["purchase.order.line"].search_read(
            [
                ("state", "in", ("purchase", "done")),
                ("company_id", "in", cids),
                ("display_type", "=", False),
                ("order_id.ai_pm_is_contractor_po", "=", False),
            ],
            ["product_qty", "qty_invoiced", "price_subtotal",
             "date_planned", "partner_id", "order_id", "company_id"],
        ):
            qty = line["product_qty"] or 0.0
            open_ratio = max(qty - (line["qty_invoiced"] or 0.0), 0.0) / qty if qty else 0.0
            open_amount = self._conv(
                shared, (line["price_subtotal"] or 0.0) * open_ratio,
                line["company_id"][0] if line["company_id"] else False)
            if open_amount <= 0:
                continue
            po_open.append({
                "amount": open_amount,
                "date_planned": (
                    fields.Date.to_date(line["date_planned"])
                    if line["date_planned"] else None
                ),
                "partner_id": line["partner_id"],
                "order_id": line["order_id"],
            })

        # Sales to Cash: SO is a forecast source only.  A posted invoice takes
        # precedence because it is represented by AR already.  Project plans
        # explicitly selected on the SO likewise take precedence over the SO.
        cfg_map = shared["cfg_map"]
        enabled = f.get("include_sales_to_cash")
        if enabled is None:
            enabled = any(cfg.include_sales_to_cash for cfg in cfg_map.values())
        f["echo"]["include_sales_to_cash"] = bool(enabled)
        sales_to_cash, sales_to_cash_review = [], []
        if enabled:
            orders = self.env["sale.order"].search([
                ("company_id", "in", cids), ("state", "in", ("sale", "done")),
                ("bsf_cash_source", "=", "sales_to_cash"),
            ])
            for order in orders:
                plans = order.bsf_delivery_plan_ids
                for line in order.order_line.filtered(lambda l: not l.display_type):
                    total_qty = line.product_uom_qty or 0.0
                    remaining_qty = max(total_qty - line.qty_invoiced, 0.0)
                    if not remaining_qty:
                        continue
                    line_plans = plans.filtered(lambda p: p.sale_line_id == line).sorted(
                        lambda p: (p.delivery_date, p.id))
                    # Allocate invoiced quantities to the earliest delivery plans.
                    # Both the plans and the fallback share one remaining balance.
                    invoiced_qty = max(line.qty_invoiced, 0.0)
                    candidates = []
                    for plan in line_plans:
                        consumed = min(plan.quantity, invoiced_qty)
                        invoiced_qty -= consumed
                        qty = min(plan.quantity - consumed, remaining_qty)
                        if qty > 0:
                            candidates.append((plan.delivery_date, qty, plan.id))
                            remaining_qty -= qty
                    if remaining_qty > 1e-6:
                        candidates.append((
                            fields.Date.to_date(order.commitment_date) if order.commitment_date else None,
                            remaining_qty, False))
                    for delivery_date, qty, plan_id in candidates:
                        amount = line.price_total * qty / total_qty if total_qty else 0.0
                        amount = order.currency_id._convert(
                            amount, order.company_id.currency_id, order.company_id,
                            f["as_of"], round=False)
                        bill_date = self._sales_to_cash_bill_date(order.partner_id, delivery_date)
                        due_date = self._sales_to_cash_due_date(order, bill_date)
                        row = {"sale_order_id": order.id, "sale_order_name": order.name,
                               "sale_line_id": line.id, "plan_id": plan_id,
                               "partner_id": order.partner_id.id, "delivery_date": delivery_date,
                               "bill_date": bill_date, "date": due_date, "amount": self._conv(shared, amount, order.company_id.id)}
                        if not delivery_date or not bill_date or not due_date or due_date < f["today"]:
                            row["reason"] = _("ไม่มีวันส่งมอบ/เครดิต หรือวันคาดรับผ่านไปแล้ว")
                            sales_to_cash_review.append(row)
                        else:
                            sales_to_cash.append(row)

        sources = {
            "plan_lines": plan_rows,
            "vendor_lines": vendor_rows,
            "retention": retention_rows,
            "po_open": po_open,
            # รายการกรอกมือ: ร่างที่ AI เสนอยังไม่นับ ต้องให้คนยืนยันก่อน
            "fc_lines": self.env["biz.smart.finance.forecast.line"].search([
                ("company_id", "in", cids), ("state", "=", "confirmed"),
            ]),
            "sales_to_cash": sales_to_cash,
            "sales_to_cash_review": sales_to_cash_review,
            "include_sales_to_cash": bool(enabled),
        }
        shared["fc_sources"] = sources
        # consumer เดิม (AP tab) อ่านคีย์นี้ตรง ๆ
        shared["po_open_lines"] = po_open
        return sources

    # ------------------------------------------------------------------
    # 13-week cash forecast (ใช้ร่วม Overview / Cash / AP)
    # ------------------------------------------------------------------
    def _build_cash_forecast(self, f, shared):
        weeks = shared["weeks"]
        today = f["today"]
        n = len(weeks)
        legs = {
            "collections": [0.0] * n,
            "sales_to_cash": [0.0] * n,
            "other_in": [0.0] * n,
            "ap": [0.0] * n,
            "payroll_opex": [0.0] * n,
            "tax_other": [0.0] * n,
        }

        def add(leg, day, amount):
            index = self._week_index(weeks, day)
            if index is not None and amount:
                legs[leg][index] += amount

        # เงินเข้า: วันนัดรับเงินจาก Collection Center ชนะ Due Date.  หนี้
        # เกินกำหนดที่ยังไม่มีนัดรับหรือมีข้อพิพาทแสดงเป็น review และไม่ทำให้
        # Base case ดูดีเกินจริง.
        followups = self.env["biz.smart.finance.collection.followup"].search([
            ("company_id", "in", f["cids"]), ("state", "=", "open"),
            ("move_line_id", "!=", False),
        ])
        followup_by_move = {row.move_line_id.id: row for row in followups}
        collection_review = []
        ar_collections = []
        for item in shared["ar_items"]:
            due = fields.Date.to_date(item["date_maturity"] or item["date"])
            followup = followup_by_move.get(item["id"]) if item.get("id") else None
            if followup and followup.promised_date and not followup.dispute:
                promised_amount = self._conv(shared, followup.promised_amount, followup.company_id.id)
                ar_collections.append({
                    "date": followup.promised_date,
                    "amount": min(item["amount_residual"], promised_amount or item["amount_residual"]),
                })
            elif due and due < today and not item.get("external"):
                collection_review.append({"move_id": item.get("move_id"), "partner_id": item.get("partner_id"),
                                          "amount": item["amount_residual"], "due_date": str(due),
                                          "reason": _("หนี้เกินกำหนดที่ยังไม่มีนัดรับเงิน")})
            else:
                ar_collections.append({"date": due, "amount": item["amount_residual"]})
        # Preserve each document and its resolved amount for both time grids.
        shared["ar_collections"] = ar_collections
        for row in ar_collections:
            add("collections", row["date"], row["amount"])
        # เงินออก: AP คงค้างตามกำหนดชำระ
        for item in shared["ap_items"]:
            add("ap", item["date_maturity"] or item["date"],
                item["amount_residual"])

        sources = self._forecast_sources(f, shared)
        for row in sources["plan_lines"]:
            add("collections", row["date"], row["amount"])
        for row in sources["sales_to_cash"]:
            add("sales_to_cash", row["date"], row["amount"])
        for row in sources["vendor_lines"]:
            add("ap", row["date"], row["amount"])
        for row in sources["retention"]:
            add(
                "collections" if row["side"] == "customer" else "ap",
                row["date"], row["amount"])
        for row in sources["po_open"]:
            add("ap", row["date_planned"] or today, row["amount"])

        # รายการกรอกมือ (เงินเดือน/ค่าใช้จ่าย/ภาษี ฯลฯ)
        fc_lines = sources["fc_lines"]
        # วนบรรทัดชั้นนอก แล้วค่อยวนสัปดาห์ — ฟิลด์ของ record (flow_type,
        # category, company_id) ถูกอ่านครั้งเดียวต่อบรรทัดแทน 13 ครั้ง
        for line in fc_lines:
            company_id = line.company_id.id
            if line.flow_type == "in":
                leg = legs["other_in"]
            elif line.category in ("payroll", "opex"):
                leg = legs["payroll_opex"]
            else:
                leg = legs["tax_other"]
            for week in weeks:
                amount = self._conv(
                    shared, line._amount_for_week(week["_from"], week["_to"]),
                    company_id)
                if amount:
                    leg[week["index"]] += amount

        # scenario: เลื่อนเงินเข้าบางส่วนออกไป (พ้น horizon = หายไปเลย — ระวังไว้ก่อน)
        fx = shared["scenario_fx"]
        delay = fx["collection_delay_pct"] / 100.0
        shift = SCENARIO_SHIFT_WEEKS.get(f["scenario"], 0)
        if delay and shift:
            shifted = [0.0] * n
            for index, amount in enumerate(legs["collections"]):
                moved = amount * delay
                shifted[index] += amount - moved
                if index + shift < n:
                    shifted[index + shift] += moved
            legs["collections"] = shifted

        # opening = เงินสดในบัญชีธนาคาร/เงินสดปัจจุบัน (cumulative ถึงวันนี้)
        opening = sum(
            shared["bal_cum"].get(account_id, 0.0)
            for account_id in shared["liquidity_ids"]
        )
        min_cash = shared["min_cash"]
        rows, closing_series, before_ap_series = [], [], []
        running = opening
        running_before_ap = opening
        alerts = []
        for week in weeks:
            i = week["index"]
            inflow = legs["collections"][i] + legs["sales_to_cash"][i] + legs["other_in"][i]
            outflow = (legs["ap"][i] + legs["payroll_opex"][i]
                       + legs["tax_other"][i])
            row_opening = running
            running += inflow - outflow
            running_before_ap += inflow - (
                legs["payroll_opex"][i] + legs["tax_other"][i])
            closing_series.append(round(running, 2))
            before_ap_series.append(round(running_before_ap, 2))
            below = min_cash and running < min_cash
            rows.append({
                "index": i,
                "label": week["label"],
                "sub": week["sub"],
                "is_actual": week["is_actual"],
                "opening": round(row_opening, 2),
                "inflow_collections": round(legs["collections"][i], 2),
                "inflow_sales_to_cash": round(legs["sales_to_cash"][i], 2),
                "inflow_other": round(legs["other_in"][i], 2),
                "outflow_ap": round(legs["ap"][i], 2),
                "outflow_payroll_opex": round(legs["payroll_opex"][i], 2),
                "outflow_tax_other": round(legs["tax_other"][i], 2),
                "closing": round(running, 2),
                "below_min": bool(below),
            })
            if below:
                alerts.append({
                    "week_index": i,
                    "label": week["label"],
                    "projected": round(running, 2),
                    "min_cash": round(min_cash, 2),
                    "gap": round(min_cash - running, 2),
                })
        return {
            "weeks": [
                {k: w[k] for k in
                 ("index", "label", "sub", "date_from", "date_to", "is_actual")}
                for w in weeks
            ],
            "opening": round(opening, 2),
            "min_cash": round(min_cash, 2),
            "closing": closing_series,
            "before_ap": before_ap_series,
            "planned_ap": [round(v, 2) for v in legs["ap"]],
            "sales_to_cash": [round(v, 2) for v in legs["sales_to_cash"]],
            "sales_to_cash_details": [{**row, "delivery_date": str(row["delivery_date"]),
                                        "bill_date": str(row["bill_date"]), "date": str(row["date"])}
                                      for row in sources["sales_to_cash"]],
            "sales_to_cash_review": [{**row, "delivery_date": str(row["delivery_date"]) if row["delivery_date"] else False,
                                       "bill_date": str(row["bill_date"]) if row["bill_date"] else False,
                                       "date": str(row["date"]) if row["date"] else False}
                                     for row in sources["sales_to_cash_review"]],
            "include_sales_to_cash": sources["include_sales_to_cash"],
            "collection_review": collection_review,
            "rows": rows,
            "alerts": alerts,
            "scenario": f["scenario"],
            "has_min_cash": bool(min_cash),
        }

    # ------------------------------------------------------------------
    # Forecast รายเดือน (เงินสด / กำไรขาดทุน / งานขาย / ต้นทุนคงเหลือ)
    # ------------------------------------------------------------------
    def _forecast_horizon(self, shared):
        values = [
            cfg.forecast_horizon_months
            for cfg in shared["cfg_map"].values()
            if cfg.forecast_horizon_months
        ]
        horizon = min(values) if values else FORECAST_MONTHS_DEFAULT
        return min(FORECAST_MONTHS_MAX, max(FORECAST_MONTHS_MIN, horizon))

    def _month_grid(self, today, horizon):
        """กริดรายเดือน + คอลัมน์ท้าย "หลังจากนี้"

        คอลัมน์ท้ายมีไว้แก้จุดอ่อนของกริด 13 สัปดาห์โดยเฉพาะ: ที่นั่นเงินที่
        ตกหลัง horizon ถูก **ทิ้งเงียบ ๆ** ทำให้ยอดรวมบนจอไม่เท่ากับยอดรวม
        ของแหล่งข้อมูล ที่นี่ทุกบาทต้องลงสักคอลัมน์เสมอ
        """
        months = []
        cursor = today.replace(day=1)
        for index in range(horizon):
            last_day = calendar.monthrange(cursor.year, cursor.month)[1]
            month_to = cursor.replace(day=last_day)
            months.append({
                "index": index,
                # ป้ายเป็น ค.ศ. สองหลัก ให้ตรงกับวันที่ ISO ที่โชว์คู่กันทั้งจอ
                "label": "%s %s" % (
                    MONTH_ABBR[cursor.month - 1], str(cursor.year)[-2:]),
                "sub": "%04d-%02d" % (cursor.year, cursor.month),
                "date_from": str(cursor),
                "date_to": str(month_to),
                # bucket แรกเริ่มนับจากวันนี้ (ที่ผ่านมาแล้วเป็นยอดจริงในบัญชี)
                "_from": today if index == 0 else cursor,
                "_to": month_to,
                "is_actual": index == 0,
                "is_tail": False,
            })
            cursor = (cursor + timedelta(days=last_day)).replace(day=1)
        months.append({
            "index": horizon,
            "label": _("หลังจากนี้"),
            "sub": "≥ %04d-%02d" % (cursor.year, cursor.month),
            "date_from": str(cursor),
            "date_to": "",
            "_from": cursor,
            "_to": date.max,
            "is_actual": False,
            "is_tail": True,
        })
        return months

    def _month_index(self, months, day):
        """เดือนของวันที่ — เกินขอบล่าง → เดือนนี้, เกินขอบบน → คอลัมน์ท้าย

        ต่างจาก `_week_index` ตรงที่ **ไม่มีวันคืน None** สำหรับวันที่จริง
        """
        if not day:
            return 0
        if day <= months[0]["_to"]:
            return 0
        for month in months[1:]:
            if month["_from"] <= day <= month["_to"]:
                return month["index"]
        return months[-1]["index"]

    def _spread_months(self, months, series, amount, start, end):
        """เกลี่ยยอดเป็นเส้นตรงตามจำนวนวันจริงในช่วง [start..end]"""
        if not amount:
            return
        if not start and not end:
            series[0] += amount
            return
        start = start or end
        end = end or start
        if end < start:
            end = start
        total_days = (end - start).days + 1
        if total_days <= 1:
            series[self._month_index(months, start)] += amount
            return
        per_day = amount / total_days
        for month in months:
            lo = max(month["_from"], start)
            hi = min(month["_to"], end)
            if lo <= hi:
                series[month["index"]] += per_day * ((hi - lo).days + 1)

    def _monthly_pl_actual(self, f, shared, date_from, date_to):
        """ยอดจริงฝั่ง P&L ในช่วงวันที่ (ใช้โชว์เทียบเดือนแรกของกริด)"""
        acc_type = shared["acc_type"]
        acc_company = shared["acc_company"]
        rows = self.env["account.move.line"]._read_group(
            [
                ("parent_state", "=", "posted"),
                ("company_id", "in", f["cids"]),
                ("account_id.account_type", "in", list(PL_TYPES)),
                ("date", ">=", str(date_from)),
                ("date", "<=", str(date_to)),
            ],
            groupby=["account_id"], aggregates=["balance:sum"],
        )
        revenue = cost = opex = 0.0
        for account, balance in rows:
            amount = self._conv(
                shared, balance or 0.0, acc_company.get(account.id))
            atype = acc_type.get(account.id)
            if atype in REVENUE_TYPES:
                revenue -= amount
            elif atype in COGS_TYPES:
                cost += amount
            elif atype in OPEX_TYPES:
                opex += amount
        return {
            "revenue": round(revenue, 2),
            "cost": round(cost, 2),
            "opex": round(opex, 2),
            "margin": round(revenue - cost - opex, 2),
        }

    @api.model
    def monthly_actual_history(self, company_ids, months=24):
        """ยอดจริงรายเดือนย้อนหลัง (รายได้/ต้นทุน/ค่าใช้จ่าย) — ป้อนให้ AI

        ไม่แปลงสกุล: ใช้เป็น "รูปแบบซ้ำ ๆ ที่เห็นในอดีต" ให้โมเดลประมาณรายการ
        ประจำ ไม่ใช่ยอดที่เอาไปโชว์บนจอ  ผู้เรียกเป็นคน gate สิทธิ์มาแล้ว
        """
        self._check_access()
        cids = [
            cid for cid in (company_ids or [])
            if cid in self.env.user.company_ids.ids
        ] or self.env.user.company_ids.ids
        months = max(1, min(36, int(months or 24)))
        today = fields.Date.context_today(self)
        start = (today.replace(day=1) - timedelta(days=31 * months)).replace(day=1)
        rows = self.env["account.move.line"].sudo()._read_group(
            [
                ("parent_state", "=", "posted"),
                ("company_id", "in", cids),
                ("account_id.account_type", "in", list(PL_TYPES)),
                ("date", ">=", str(start)),
                ("date", "<", str(today.replace(day=1))),
            ],
            groupby=["date:month", "account_id"],
            aggregates=["balance:sum"],
        )
        acc_type = {
            a["id"]: a["account_type"]
            for a in self.env["account.account"].sudo().search_read(
                [("company_id", "in", cids)], ["account_type"])
        }
        buckets = defaultdict(lambda: {"revenue": 0.0, "cogs": 0.0, "opex": 0.0})
        for period, account, balance in rows:
            key = str(period)[:7] if period else ""
            if not key:
                continue
            atype = acc_type.get(account.id)
            amount = balance or 0.0
            if atype in REVENUE_TYPES:
                buckets[key]["revenue"] -= amount
            elif atype in COGS_TYPES:
                buckets[key]["cogs"] += amount
            elif atype in OPEX_TYPES:
                buckets[key]["opex"] += amount
        return [
            {"month": key, **{k: round(v, 2) for k, v in values.items()}}
            for key, values in sorted(buckets.items())
        ][-months:]

    def _build_forecast(self, f, shared):
        """พยากรณ์รายเดือน 3 ชั้น — เงินสด / กำไรขาดทุน / งานขาย / ต้นทุนคงเหลือ

        **สามชั้นของความแน่นอน** (ผสมกันได้แต่ต้องแยกให้เห็นบนจอ):

        1. ผูกพันแล้ว — แผนวางบิลลูกค้า, แผนจ่ายผู้รับเหมา, PO, เงินประกัน,
           มูลค่างานตามสัญญาที่ยังไม่รับรู้, ต้นทุนคงเหลือ (EAC − ที่ใช้ไป)
        2. งานขายที่ยังไม่เซ็น — ดีล × ความน่าจะเป็น กระจายตามแบบแผนวางบิล
        3. รายการประจำที่กรอกมือ — เงินเดือน/ค่าเช่า/ภาษี

        **ตารางกันนับซ้ำ** (ทุกบรรทัดคือบั๊กที่เคยเกิดได้จริง):

        | แหล่ง | นับเมื่อ | เลิกนับเมื่อ |
        |---|---|---|
        | ลูกหนี้/เจ้าหนี้คงค้าง | ลงบัญชีแล้ว ยังไม่ตัดชำระ | ตัดชำระแล้ว |
        | แผนวางบิลลูกค้า | ยังไม่วางบิล | วางบิลแล้ว → เป็นลูกหนี้ |
        | แผนจ่ายผู้รับเหมา | ยังไม่มี vendor bill | ตั้งบิลแล้ว → เป็นเจ้าหนี้ |
        | PO วัสดุ | ส่วนที่ยังไม่ตั้งบิล | ตั้งบิลแล้ว → เป็นเจ้าหนี้ |
        | งบ BOQ | ยังไม่มี PO และเกินยอดแผนจ่ายของโครงการ | เปิด PO/แผนจ่ายแล้ว |
        | ดีล (ชั้น 2) | ขั้นยังไม่ชนะ | ชนะ → บังคับผูกโครงการ ชั้น 1 รับช่วง |
        | รายการกรอกมือ | สถานะ "ใช้งาน" | ยังเป็นร่างที่ AI เสนอ |
        | มูลค่างานตามสัญญา | เฉพาะงานที่ถือมูลค่า (`carries_boq_value`) | รับรู้ครบ 100% |
        """
        cids = f["cids"]
        today = f["today"]
        horizon = self._forecast_horizon(shared)
        months = self._month_grid(today, horizon)
        n = len(months)
        sources = self._forecast_sources(f, shared)
        project_company = shared["project_company"]
        conv = lambda amount, project_id: self._conv(
            shared, amount, project_company.get(project_id))
        zeros = lambda: [0.0] * n

        legs = {key: zeros() for key in (
            "collections", "sales_to_cash", "pipeline_in", "other_in",
            "ap_committed", "boq_budget", "pipeline_cost",
            "payroll_opex", "tax_other",
        )}

        def add(leg, day, amount):
            if amount:
                legs[leg][self._month_index(months, day)] += amount

        # ---- ชั้น 1: เงินเข้า/ออกที่ผูกพันแล้ว ----
        for row in shared.get("ar_collections", []):
            if row["date"]:
                add("collections", row["date"], row["amount"])
        for item in shared["ap_items"]:
            add("ap_committed", item["date_maturity"] or item["date"],
                item["amount_residual"])

        # แผนวางบิล: กริดรายเดือนใช้ "วันคาดเก็บเงิน" ไม่ใช่วันวางบิล เพราะ
        # ระยะเครดิตลูกค้ากินเวลาข้ามเดือนจนเปลี่ยนรูปกราฟ (กริดรายสัปดาห์
        # มองใกล้พอที่จะใช้วันวางบิลดิบได้)
        collect_days = {
            c.id: c.ai_pm_customer_collect_days or 0
            for c in self.env["res.company"].browse(cids)
        }
        for row in sources["plan_lines"]:
            lag = collect_days.get(project_company.get(row["project_id"]), 0)
            add("collections", row["date"] + timedelta(days=lag), row["amount"])
        for row in sources["sales_to_cash"]:
            add("sales_to_cash", row["date"], row["amount"])
        for row in sources["vendor_lines"]:
            add("ap_committed", row["date"], row["amount"])
        for row in sources["retention"]:
            add(
                "collections" if row["side"] == "customer" else "ap_committed",
                row["date"], row["amount"])
        for row in sources["po_open"]:
            add("ap_committed", row["date_planned"] or today, row["amount"])

        # ---- ชั้น 1 (ต่อ): งบ BOQ ที่ยังไม่ผูกพันเป็นเอกสาร ----
        projects = shared.get("projects")
        if projects is None:
            projects = self.env["project.project"].search([
                ("company_id", "in", cids), ("active", "=", True),
            ])
            shared["projects"] = projects
        vendor_plan_by_project = defaultdict(float)
        for row in sources["vendor_lines"]:
            vendor_plan_by_project[row["project_id"]] += row["amount"]
        boq_rows = self.env["ai.pm.boq.line"].search_read(
            [
                ("project_id", "in", projects.ids),
                ("budget_amount", ">", 0),
                ("purchase_order_id", "=", False),
            ],
            ["project_id", "budget_amount", "budget_date"],
        )
        boq_raw = defaultdict(float)
        for row in boq_rows:
            project_id = row["project_id"][0] if row["project_id"] else 0
            boq_raw[project_id] += conv(row["budget_amount"], project_id)
        # แผนจ่ายผู้รับเหมาบางงวดมาจากงาน BOQ ที่ยังไม่มี PO ผูกกลับมา จึงหัก
        # ยอดที่มีแผนจ่ายแล้วออกทั้งโครงการก่อน (ตัดที่ 0 ไม่ให้ติดลบ)
        boq_factor = {
            pid: max(raw - vendor_plan_by_project.get(pid, 0.0), 0.0) / raw
            for pid, raw in boq_raw.items() if raw
        }
        for row in boq_rows:
            project_id = row["project_id"][0] if row["project_id"] else 0
            amount = conv(row["budget_amount"], project_id) * boq_factor.get(
                project_id, 0.0)
            add("boq_budget", row["budget_date"] or today, amount)

        # ---- ชั้น 2: งานขายที่ยังไม่เซ็น ----
        cfg_map = shared["cfg_map"]
        deals = self.env["biz.smart.finance.deal"].search([
            ("company_id", "in", cids), ("stage", "in", list(OPEN_STAGES)),
        ])
        pipeline_rows = []
        pipeline_weighted_by_month = zeros()
        pipeline_revenue = zeros()
        pipeline_cost_pl = zeros()
        for deal in deals:
            company_id = deal.company_id.id
            cfg = cfg_map.get(company_id)
            margin_default = (
                cfg.pipeline_default_margin_pct if cfg else 0.0) or 30.0
            cost_lag = cfg.pipeline_cost_lag_months if cfg else 0
            money = lambda v: self._conv(shared, v, company_id)
            for day, amount in deal._phase(
                "cash_in", collect_days.get(company_id, 0), margin_default,
                cost_lag,
            ):
                converted = money(amount)
                add("pipeline_in", day, converted)
                pipeline_weighted_by_month[
                    self._month_index(months, day)] += converted
            for day, amount in deal._phase(
                "revenue", 0, margin_default, cost_lag,
            ):
                pipeline_revenue[self._month_index(months, day)] += money(amount)
            for day, amount in deal._phase(
                "cost", 0, margin_default, cost_lag,
            ):
                converted = money(amount)
                add("pipeline_cost", day, converted)
                pipeline_cost_pl[self._month_index(months, day)] += converted
            pipeline_rows.append({
                "id": deal.id,
                "name": deal.name,
                "customer": deal.partner_id.name or deal.customer_name or "",
                "stage": deal.stage,
                "stage_label": dict(
                    deal._fields["stage"].selection).get(deal.stage, ""),
                "amount": round(money(deal.amount), 2),
                "probability": deal.probability,
                "weighted": round(money(deal.weighted_amount), 2),
                "sign_date": str(deal.expected_sign_date),
                "duration_months": deal.duration_months,
                "pattern": deal.billing_pattern_id.name or "",
                "margin_pct": round(
                    deal._margin_pct(margin_default), 1),
            })

        # ---- ชั้น 3: รายการประจำที่กรอกมือ ----
        # วนบรรทัดชั้นนอกเช่นเดียวกับกริดรายสัปดาห์ — horizon ยาวถึง 18 เดือน
        # การอ่านฟิลด์ของ record ซ้ำจึงแพงกว่าเดิมอีกเท่าตัว
        for line in sources["fc_lines"]:
            company_id = line.company_id.id
            if line.flow_type == "in":
                leg = legs["other_in"]
            elif line.category in ("payroll", "opex"):
                leg = legs["payroll_opex"]
            else:
                leg = legs["tax_other"]
            for month in months:
                amount = self._conv(
                    shared,
                    line._amount_for_month(month["_from"], month["_to"]),
                    company_id)
                if amount:
                    leg[month["index"]] += amount

        # ฐานของแท็บ Risk = ขาเงินสด "ก่อน" ปรับ scenario — แท็บนั้นปั้นเส้น
        # เงินสดของทั้งสาม scenario เองจากฐานเดียวกันนี้ (ดู _build_risk)
        base_legs = {key: list(values) for key, values in legs.items()}

        # ---- scenario: เลื่อนเงินเข้าบางส่วน (ตกเกินขอบ = ไปคอลัมน์ท้าย) ----
        fx = shared["scenario_fx"]
        delay = fx["collection_delay_pct"] / 100.0
        shift = SCENARIO_SHIFT_MONTHS.get(f["scenario"], 0)
        if delay and shift:
            for key in ("collections", "sales_to_cash", "pipeline_in"):
                shifted = zeros()
                for index, amount in enumerate(legs[key]):
                    moved = amount * delay
                    shifted[index] += amount - moved
                    shifted[min(index + shift, n - 1)] += moved
                legs[key] = shifted

        # ---- กระแสเงินสดสะสม ----
        opening = sum(
            shared["bal_cum"].get(account_id, 0.0)
            for account_id in shared["liquidity_ids"]
        )
        min_cash = shared["min_cash"]
        rows, closing_series, net_series = [], [], []
        inflow_series, outflow_series = [], []
        alerts = []
        running = opening
        for month in months:
            i = month["index"]
            inflow = (legs["collections"][i] + legs["sales_to_cash"][i] + legs["pipeline_in"][i]
                      + legs["other_in"][i])
            outflow = (legs["ap_committed"][i] + legs["boq_budget"][i]
                       + legs["pipeline_cost"][i] + legs["payroll_opex"][i]
                       + legs["tax_other"][i])
            row_opening = running
            running += inflow - outflow
            below = bool(min_cash and running < min_cash and not month["is_tail"])
            inflow_series.append(round(inflow, 2))
            outflow_series.append(round(outflow, 2))
            net_series.append(round(inflow - outflow, 2))
            closing_series.append(round(running, 2))
            rows.append({
                "index": i,
                "label": month["label"],
                "sub": month["sub"],
                "is_tail": month["is_tail"],
                "opening": round(row_opening, 2),
                "in_collections": round(legs["collections"][i], 2),
                "in_sales_to_cash": round(legs["sales_to_cash"][i], 2),
                "in_pipeline": round(legs["pipeline_in"][i], 2),
                "in_other": round(legs["other_in"][i], 2),
                "out_ap": round(legs["ap_committed"][i], 2),
                "out_boq": round(legs["boq_budget"][i], 2),
                "out_pipeline": round(legs["pipeline_cost"][i], 2),
                "out_payroll_opex": round(legs["payroll_opex"][i], 2),
                "out_tax_other": round(legs["tax_other"][i], 2),
                "net": round(inflow - outflow, 2),
                "closing": round(running, 2),
                "below_min": below,
            })
            if below:
                alerts.append({
                    "month_index": i,
                    "label": month["label"],
                    "projected": round(running, 2),
                    "min_cash": round(min_cash, 2),
                    "gap": round(min_cash - running, 2),
                })

        # ---- P&L: รับรู้รายได้ตามแผนงาน + ต้นทุนคงเหลือ ----
        revenue_backlog = zeros()
        cost_project = zeros()
        project_end = {}
        task_rows = self.env["project.task"].search_read(
            [
                ("project_id", "in", projects.ids),
                ("carries_boq_value", "=", True),
                ("contract_value", ">", 0),
            ],
            ["project_id", "contract_value", "value_percent",
             "planned_date_start", "date_deadline"],
        )
        for row in task_rows:
            project_id = row["project_id"][0] if row["project_id"] else 0
            remaining = (row["contract_value"] or 0.0) * max(
                100.0 - (row["value_percent"] or 0.0), 0.0) / 100.0
            start = (fields.Datetime.to_datetime(row["planned_date_start"]).date()
                     if row["planned_date_start"] else None)
            end = (fields.Datetime.to_datetime(row["date_deadline"]).date()
                   if row["date_deadline"] else None)
            if end and (project_id not in project_end or end > project_end[project_id]):
                project_end[project_id] = end
            if start and start < today:
                start = today
            self._spread_months(
                months, revenue_backlog, conv(remaining, project_id), start, end)

        ctc_rows = []
        ctc_total = 0.0
        for row in shared.get("margin_rows") or []:
            project_id = row["project_id"]
            ctc = row["cost_to_complete"] or 0.0
            eac, cost_to_date = shared.get("eac_by_project", {}).get(
                project_id, (0.0, 0.0))
            end = project_end.get(project_id)
            overdue = bool(ctc > 0 and end and end < today)
            self._spread_months(
                months, cost_project, ctc, today if not overdue else None, end)
            if ctc <= 0:
                continue
            ctc_total += ctc
            months_left = max(
                ((end - today).days / 30.0) if end and end > today else 0.0, 0.0)
            ctc_rows.append({
                "project_id": project_id,
                "name": row["name"],
                "company": row["company"],
                "budget_total": row["budget_total"],
                "eac": round(conv(eac, project_id), 2),
                "cost_to_date": round(conv(cost_to_date, project_id), 2),
                "cost_to_complete": round(ctc, 2),
                "end_date": str(end) if end else "",
                "months_left": round(months_left, 1),
                "run_rate": round(ctc / months_left, 2) if months_left else 0.0,
                # แผนจบไปแล้วแต่ต้นทุนยังไม่ครบ = ต้องจ่ายทันที ไม่ใช่ทยอยจ่าย
                "schedule_overdue": overdue,
            })
        ctc_rows.sort(key=lambda r: -r["cost_to_complete"])

        opex_series = [
            legs["payroll_opex"][i] + legs["tax_other"][i] for i in range(n)]
        other_income = list(legs["other_in"])
        revenue_series = [
            revenue_backlog[i] + pipeline_revenue[i] + other_income[i]
            for i in range(n)
        ]
        cost_series = [
            cost_project[i] + pipeline_cost_pl[i] + opex_series[i]
            for i in range(n)
        ]
        margin_series = [revenue_series[i] - cost_series[i] for i in range(n)]
        margin_pct_series = [
            round(margin_series[i] / revenue_series[i] * 100.0, 1)
            if revenue_series[i] else None
            for i in range(n)
        ]
        month0_start = today.replace(day=1)

        rnd = lambda series: [round(v, 2) for v in series]
        pipeline_amount_total = sum(r["amount"] for r in pipeline_rows)
        pipeline_weighted_total = sum(r["weighted"] for r in pipeline_rows)
        # "เดือนที่ต่ำสุด" ต้องเป็นเดือนจริง — คอลัมน์ท้ายเป็นยอดสะสมของทุกอย่าง
        # ที่เลย horizon จึงต่ำที่สุดแทบทุกครั้งและไม่ได้บอกอะไรเชิงเดือน
        real_months = [m["index"] for m in months if not m["is_tail"]]
        low_index = min(real_months, key=lambda i: closing_series[i])
        # ฐานรายเดือนสำหรับ Key Outcome / Sensitivity ของแท็บ Risk
        # (คอลัมน์ท้าย "หลังจากนี้" ตัดทิ้ง — ไม่ใช่เดือนจริง ดู _month_grid)
        shared["fc_basis"] = {
            "months": [
                {"label": m["label"], "sub": m["sub"]}
                for m in months if not m["is_tail"]
            ],
            "opening": opening,
            "min_cash": min_cash,
            "legs": {
                key: [values[i] for i in real_months]
                for key, values in base_legs.items()
            },
            "revenue": [revenue_series[i] for i in real_months],
            "pipeline_revenue": [pipeline_revenue[i] for i in real_months],
            "project_cost": [
                cost_project[i] + pipeline_cost_pl[i] for i in real_months],
            "opex": [opex_series[i] for i in real_months],
        }
        return {
            "months": [
                {k: m[k] for k in
                 ("index", "label", "sub", "date_from", "date_to",
                  "is_actual", "is_tail")}
                for m in months
            ],
            "horizon_months": horizon,
            "scenario": f["scenario"],
            "cash": {
                "opening": round(opening, 2),
                "min_cash": round(min_cash, 2),
                "has_min_cash": bool(min_cash),
                "inflow": inflow_series,
                "outflow": outflow_series,
                "net": net_series,
                "closing": closing_series,
                "rows": rows,
                "alerts": alerts,
                "low_month": {
                    "label": months[low_index]["label"],
                    "closing": closing_series[low_index],
                } if n else {},
            },
            "pnl": {
                "revenue_backlog": rnd(revenue_backlog),
                "revenue_pipeline": rnd(pipeline_revenue),
                "other_income": rnd(other_income),
                "revenue": rnd(revenue_series),
                "cost_project": rnd(cost_project),
                "cost_pipeline": rnd(pipeline_cost_pl),
                "opex": rnd(opex_series),
                "cost": rnd(cost_series),
                "margin": rnd(margin_series),
                "margin_pct": margin_pct_series,
                "total": {
                    "revenue": round(sum(revenue_series), 2),
                    "cost": round(sum(cost_series), 2),
                    "margin": round(sum(margin_series), 2),
                    "margin_pct": round(
                        sum(margin_series) / sum(revenue_series) * 100.0, 1)
                    if sum(revenue_series) else None,
                },
                "actual_mtd": self._monthly_pl_actual(
                    f, shared, month0_start, today),
                "actual_label": "%s (1–%s)" % (months[0]["label"], today.day),
            },
            "pipeline": {
                "rows": sorted(pipeline_rows, key=lambda r: r["sign_date"]),
                "weighted_by_month": rnd(pipeline_weighted_by_month),
                "totals": {
                    "count": len(pipeline_rows),
                    "amount": round(pipeline_amount_total, 2),
                    "weighted": round(pipeline_weighted_total, 2),
                },
                "revenue_share_pct": round(
                    sum(pipeline_revenue) / sum(revenue_series) * 100.0, 1)
                if sum(revenue_series) else 0.0,
            },
            "ctc": {
                "rows": ctc_rows[:25],
                "total": round(ctc_total, 2),
                "overdue_count": sum(
                    1 for r in ctc_rows if r["schedule_overdue"]),
            },
        }

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------
    def _yoy(self, current, prior):
        if not prior:
            return None
        return round((current - prior) / abs(prior) * 100.0, 1)

    def _type_index(self, shared, key):
        """{(company_id, account_type): ยอดรวม} ของ dict ยอดคงเหลือหนึ่งใบ

        `_sum_type`/`_sum_type_co`/`_equity_co` เดิมวน dict **ทั้งใบ** ทุกครั้ง
        และถูกเรียกหลายสิบครั้งต่อการโหลด (งบกระแสเงินสด, อัตราส่วนต่อบริษัท,
        CCC) — กลุ่มบัญชีใหญ่ ๆ จึงกลายเป็นหลักแสน iteration ต่อจอ
        สร้าง index ครั้งเดียวต่อ key แล้วบวกเฉพาะ bucket ที่ต้องใช้

        cache ผูกกับชื่อ key ได้เพราะผู้เรียกทั้งหมดใช้ `bal_*` ที่ประกอบเสร็จ
        แล้วใน `_build_shared` และไม่ถูกเขียนทับอีก (คีย์ชั่วคราวของแท็บ
        Compare เช่น `_cmp_flow` ไม่ได้เดินผ่านเมธอดกลุ่มนี้)"""
        cache = shared.setdefault("_type_index", {})
        if key not in cache:
            index = defaultdict(float)
            acc_type = shared["acc_type"]
            acc_company = shared["acc_company"]
            for account_id, balance in shared[key].items():
                index[(acc_company.get(account_id),
                       acc_type.get(account_id))] += balance
            cache[key] = dict(index)
        return cache[key]

    def _sum_type(self, shared, key, types):
        index = self._type_index(shared, key)
        return sum(
            balance for (_cid, atype), balance in index.items()
            if atype in types
        )

    def _capital_structure(self, shared):
        """เงินสด / หนี้มีดอกเบี้ย / ส่วนของผู้ถือหุ้น + เป้า Net Debt/Equity

        Overview กับ Risk (Covenant Headroom) ต้องอ่านจากที่เดียวกัน ไม่งั้น
        สองจอบอกฐานทุนคนละตัวทั้งที่เป็นตัวเลขเดียวกัน
        """
        cash_balance = sum(
            shared["bal_cum"].get(a, 0.0) for a in shared["liquidity_ids"]
        )
        # Net debt: บัญชีเงินกู้ที่ map ไว้ (เครดิต → balance ติดลบ) − เงินสด
        # (Odoo M2M ∪ ธงบัญชีภายนอก — เตรียมไว้แล้วใน _build_shared)
        debt_ids = shared["debt_ids"]
        debt = -sum(shared["bal_cum"].get(a, 0.0) for a in debt_ids)
        # ส่วนของผู้ถือหุ้น = ยอดสะสม (เครดิต) + กำไรปีนี้ที่ยังไม่ปิดงบ
        equity = (-self._sum_type(shared, "bal_cum", EQUITY_TYPES)
                  + shared["pl_ytd"]["total"]["net"])
        targets = [
            cfg.net_debt_equity_target
            for cfg in shared["cfg_map"].values() if cfg.net_debt_equity_target
        ]
        return {
            "cash": cash_balance,
            "debt": debt,
            "net_debt": debt - cash_balance,
            "equity": equity,
            "debt_configured": bool(debt_ids),
            "nde_target": (
                round(sum(targets) / len(targets), 2) if targets else None),
        }

    @staticmethod
    def _dim(dim_id, label, icon, value, fmt, sub, note, status):
        """หนึ่งการ์ดมิติบน control tower — สถานะตัดสินที่ engine ตาม
        กติกา odoo-owl-dashboards (ห้ามคำนวณ good/warn/risk ใน template)"""
        return {
            "id": dim_id, "label": label, "icon": icon,
            "value": value, "fmt": fmt, "sub": sub or "",
            "note": note or "", "status": status,
        }

    def _overview_dimensions(self, f, shared, tabs, ratio_summary):
        """11 มิติ = 11 แท็บที่เหลือ ย่อเหลือ headline เดียว + ไฟสถานะ"""
        dims = []

        # --- เงินสด & สภาพคล่อง ---
        cash_kpis = tabs["cash"]["kpis"]
        alert = tabs["cash"]["min_cash_alert"]
        if alert["count"]:
            cash_status, cash_note = "risk", _(
                "เงินสดหลุดขั้นต่ำ %s สัปดาห์ (%s–%s)") % (
                alert["count"], alert["first_label"], alert["last_label"])
        elif alert["has_min_cash"] and alert["min_cash"] and (
                cash_kpis["min_13w"] - alert["min_cash"]
        ) < alert["min_cash"] * 0.1:
            cash_status, cash_note = "warn", _("เงินสดต่ำสุดใกล้ระดับขั้นต่ำ")
        else:
            cash_status, cash_note = "good", _("เหนือระดับเงินสดขั้นต่ำตลอด 13 สัปดาห์")
        dims.append(self._dim(
            "cash", _("เงินสด & สภาพคล่อง"), "fa-tint",
            cash_kpis["min_13w"], "money",
            _("ต่ำสุด 13 สัปดาห์ · %s") % (cash_kpis["min_13w_label"] or "—"),
            cash_note, cash_status))

        # --- ยอดขาย → เงินสด (DSO) ---
        sm = tabs["sales"]["metrics"]
        dso, target = sm["dso_days"], sm["dso_target"]
        if dso is None:
            sales_status, sales_note = "neutral", _("ยังไม่มีข้อมูล DSO")
        elif target is not None and dso > target + 15:
            sales_status, sales_note = "risk", _("DSO เกินเป้า %s วัน") % round(dso - target)
        elif target is not None and dso > target:
            sales_status, sales_note = "warn", _("DSO สูงกว่าเป้าเล็กน้อย")
        else:
            sales_status, sales_note = "good", _("เก็บเงินได้ตามเป้า")
        dims.append(self._dim(
            "sales", _("ยอดขาย → เงินสด"), "fa-filter",
            dso, "days",
            _("เป้า %s วัน · ลูกหนี้ %s") % (
                round(target) if target is not None else "—",
                self._fmt_compact(sm["total_ar"])),
            sales_note, sales_status))

        # --- เจ้าหนี้ & แผนจ่าย ---
        ap = tabs["ap"]
        if ap["conflict"]["has_conflict"]:
            ap_status, ap_note = "risk", _("มีสัปดาห์ที่เงินไม่พอจ่ายเจ้าหนี้")
        elif ap["overdue_total"] > 0:
            ap_status, ap_note = "warn", _("มีเจ้าหนี้เกินกำหนดค้างอยู่")
        else:
            ap_status, ap_note = "good", _("ไม่มีเจ้าหนี้เกินกำหนด")
        dims.append(self._dim(
            "ap", _("เจ้าหนี้ & แผนจ่าย"), "fa-credit-card",
            ap["aging"]["total"], "money",
            _("เกินกำหนด %s · ผูกพัน PO %s") % (
                self._fmt_compact(ap["overdue_total"]),
                self._fmt_compact(ap["committed_po"].get("total", 0.0))),
            ap_note, ap_status))

        # --- กำไรโครงการ ---
        lk = tabs["margin"]["leakage"]
        if lk["alert"]:
            m_status, m_note = "risk", _("Margin หลุดงบเกินเพดาน %.1f%%") % (
                lk["threshold"] or 0.0)
        elif (lk["leakage_pct"] or 0.0) > 0:
            m_status, m_note = "warn", _("Margin คาดการณ์ต่ำกว่างบ")
        else:
            m_status, m_note = "good", _("Margin คาดการณ์เป็นไปตามงบ")
        dims.append(self._dim(
            "margin", _("กำไรโครงการ"), "fa-bullseye",
            lk["leakage_pct"], "pct",
            _("รั่วไหล %s") % self._fmt_compact(lk["leakage_amount"]),
            m_note, m_status))

        # --- พยากรณ์รายเดือน ---
        fc_cash = tabs["forecast"]["cash"]
        fc_low = fc_cash.get("low_month") or {}
        fc_margin_pct = tabs["forecast"]["pnl"]["total"].get("margin_pct")
        if fc_cash.get("alerts"):
            fc_status, fc_note = "risk", _("คาดว่าเงินสดจะหลุดขั้นต่ำในช่วงพยากรณ์")
        elif fc_margin_pct is not None and fc_margin_pct < 0:
            fc_status, fc_note = "warn", _("Margin รวมช่วงพยากรณ์ติดลบ")
        else:
            fc_status, fc_note = "good", _("กระแสเงินสดพยากรณ์เป็นบวกตลอดช่วง")
        dims.append(self._dim(
            "forecast", _("พยากรณ์รายเดือน"), "fa-line-chart",
            fc_low.get("closing"), "money",
            _("เงินสดต่ำสุด %s · margin %s") % (
                fc_low.get("label") or "—",
                "%.1f%%" % fc_margin_pct if fc_margin_pct is not None else "—"),
            fc_note, fc_status))

        # --- สินค้าคงคลัง ---
        ik = tabs["inventory"]["kpis"]
        if ik["recon_shown"] and not ik["recon_ok"]:
            inv_status, inv_note = "warn", _("SVL กับ GL ไม่กระทบยอด (%s)") % (
                self._fmt_compact(ik["recon_diff"]))
        elif ik["dio_days"] is None and ik["total_value"] is None:
            inv_status, inv_note = "neutral", _("ยังไม่มีข้อมูลสต๊อก")
        else:
            inv_status, inv_note = "good", _("มูลค่าสต๊อกกระทบยอดกับ GL")
        dims.append(self._dim(
            "inventory", _("สินค้าคงคลัง"), "fa-cubes",
            ik["dio_days"], "days",
            _("มูลค่า %s · หมุน %s รอบ") % (
                self._fmt_compact(ik["total_value"]),
                ik["turnover"] if ik["turnover"] is not None else "—"),
            inv_note, inv_status))

        # --- อัตราส่วนทางการเงิน ---
        cr = ratio_summary.get("current_ratio")
        de = ratio_summary.get("debt_to_equity")
        if cr is not None and cr < 1.0:
            r_status, r_note = "risk", _("Current ratio ต่ำกว่า 1.0")
        elif cr is not None and cr < 1.5:
            r_status, r_note = "warn", _("Current ratio ต่ำกว่า 1.5")
        else:
            r_status, r_note = "good", _("สภาพคล่องตามอัตราส่วนอยู่ในเกณฑ์ดี")
        dims.append(self._dim(
            "ratios", _("อัตราส่วนทางการเงิน"), "fa-percent",
            cr, "x",
            _("D/E %s · Net margin %s") % (
                de if de is not None else "—",
                "%.1f%%" % ratio_summary["net_margin_pct"]
                if ratio_summary.get("net_margin_pct") is not None else "—"),
            r_note, r_status))

        # --- Controlling (ศูนย์ต้นทุน) ---
        ct = tabs["controlling"]
        util = (ct.get("totals") or {}).get("utilization_pct")
        over = (ct.get("totals") or {}).get("over_count") or 0
        if not ct.get("configured"):
            c_status, c_note = "neutral", _("ยังไม่ได้ตั้งมิติศูนย์ต้นทุน")
        elif util is not None and util > 100:
            c_status, c_note = "risk", _("ใช้งบเกิน 100%")
        elif over:
            c_status, c_note = "warn", _("มีศูนย์ต้นทุนเกินงบ %s รายการ") % over
        else:
            c_status, c_note = "good", _("ทุกศูนย์ต้นทุนอยู่ในงบ")
        dims.append(self._dim(
            "controlling", _("Controlling"), "fa-sitemap",
            util, "pct",
            _("คงเหลือ %s") % self._fmt_compact(
                (ct.get("totals") or {}).get("available", 0.0)),
            c_note, c_status))

        # --- งบการเงิน ---
        st = tabs["statements"]
        bs_check = st["balance_sheet"]["check"]
        cf = st["cashflow"]
        if abs(bs_check or 0.0) > 1.0:
            s_status, s_note = "warn", _("งบดุลไม่ลงตัว (ผลต่าง %s)") % (
                self._fmt_compact(bs_check))
        else:
            s_status, s_note = "good", _("งบดุลลงตัว")
        dims.append(self._dim(
            "statements", _("งบการเงิน"), "fa-file-text-o",
            cf["net_change"], "money",
            _("เงินสดปลายงวด %s") % self._fmt_compact(cf["closing_cash"]),
            s_note, s_status))

        # --- เปรียบเทียบหลายงวด (BI) ---
        if not f["echo"].get("compare_mode"):
            dims.append(self._dim(
                "compare", _("เปรียบเทียบหลายงวด"), "fa-columns",
                None, "money", _("ปิดอยู่"),
                _("เปิดโหมดเทียบจากแถบเครื่องมือเพื่อดูแนวโน้ม 2–6 งวด"),
                "neutral"))
        else:
            cmp_rows = {r["key"]: r for r in tabs["compare"].get("pnl_rows", [])}
            rev_deltas = (
                cmp_rows.get("revenue_op") or {}).get("delta_pct") or []
            delta = rev_deltas[-1] if rev_deltas else None
            cmp_status = "good" if (delta or 0.0) >= 0 else "warn"
            dims.append(self._dim(
                "compare", _("เปรียบเทียบหลายงวด"), "fa-columns",
                delta, "pct",
                _("รายได้เทียบงวดก่อน"),
                _("เทียบ %s งวด") % f["echo"].get("compare_count", 0),
                cmp_status))

        # --- ความเสี่ยง & สถานการณ์ ---
        risk_tab = tabs["risk"]
        outcomes = risk_tab.get("outcomes") or {}
        # ช่วงเวลาที่ engine คำนวณได้ยาวสุด (อาจสั้นกว่า 12 ถ้าฐานพยากรณ์ไม่ครบ)
        horizon_key = max(outcomes, key=int) if outcomes else None
        base_outcome = (outcomes.get(horizon_key) or {}).get("base") or {}
        runway = base_outcome.get("runway_months")
        levels = {r.get("level") for r in self._auto_alerts(f, shared)}
        open_risks = self.env["biz.smart.finance.risk"].search_count([
            ("company_id", "in", f["cids"]), ("state", "=", "open")])
        if "high" in levels or (runway is not None and runway < 3):
            k_status, k_note = "risk", _("มีสัญญาณเตือนระดับสูง")
        elif "medium" in levels or open_risks:
            k_status, k_note = "warn", _("มีความเสี่ยงที่ต้องติดตาม")
        else:
            k_status, k_note = "good", _("ไม่มีสัญญาณเตือนเร่งด่วน")
        dims.append(self._dim(
            "risk", _("ความเสี่ยง & สถานการณ์"), "fa-exclamation-triangle",
            open_risks, "int",
            _("Cash runway %s เดือน · headroom %s") % (
                runway if runway is not None else "∞",
                self._fmt_compact(base_outcome.get("headroom"))),
            k_note, k_status))

        return dims

    @staticmethod
    def _fmt_compact(value):
        """ย่อเงินเป็นข้อความสั้นสำหรับ note/sub (K/M) — client ยัง scale เอง
        ไม่ได้เพราะเป็นข้อความประกอบแล้ว จึงย่อที่นี่แบบอ่านง่าย"""
        if value is None:
            return "—"
        magnitude = abs(value)
        if magnitude >= 1000000:
            return "%.1fM" % (value / 1000000.0)
        if magnitude >= 1000:
            return "%.0fK" % (value / 1000.0)
        return "%.0f" % value

    def _build_overview(self, f, shared, tabs):
        pl = shared["pl_ytd"]["total"]
        prior = shared["pl_prior"]["total"]
        capital = self._capital_structure(shared)
        cash_balance = capital["cash"]
        net_debt = capital["net_debt"]
        equity = capital["equity"]
        nde_ratio = round(net_debt / equity, 2) if equity else None
        nde_target = capital["nde_target"]

        ratio_summary = tabs["ratios"].get("summary", {})
        cash_kpis = tabs["cash"]["kpis"]
        min_alert = tabs["cash"]["min_cash_alert"]

        # ตาราง BU (= บริษัท) — backlog ต่อบริษัทเตรียมไว้แล้วใน _build_shared
        backlog_by_company = shared["backlog_by_company"]
        companies = self.env["res.company"].browse(f["cids"])
        bu_table = []
        for company in companies:
            bucket = shared["pl_ytd"]["by_company"].get(company.id, {})
            revenue = bucket.get("revenue", 0.0)
            ebitda = bucket.get("ebitda", 0.0)
            bu_table.append({
                "company_id": company.id,
                "name": company.name,
                "revenue_ytd": round(revenue, 2),
                "ebitda": round(ebitda, 2),
                "ebitda_margin_pct": round(ebitda / revenue * 100.0, 1) if revenue else 0.0,
                "backlog": round(backlog_by_company.get(company.id, 0.0), 2),
                "cash": round(self._sum_type_co(
                    shared, "bal_cum", ("asset_cash",), company.id), 2),
                "ar": round(self._sum_type_co(
                    shared, "bal_cum", (AR_TYPE,), company.id), 2),
                "ap": round(-self._sum_type_co(
                    shared, "bal_cum", (AP_TYPE,), company.id), 2),
                "ccc_days": self._ccc_days(f, shared, company.id),
            })

        return {
            "kpis": {
                "revenue_ytd": round(pl["revenue"], 2),
                "revenue_yoy_pct": self._yoy(pl["revenue"], prior["revenue"]),
                "ebitda_ytd": round(pl["ebitda"], 2),
                "ebitda_yoy_pct": self._yoy(pl["ebitda"], prior["ebitda"]),
                "ebitda_margin_pct": round(
                    pl["ebitda"] / pl["revenue"] * 100.0, 1
                ) if pl["revenue"] else 0.0,
                "net_profit_ytd": round(pl["net"], 2),
                "net_profit_yoy_pct": self._yoy(pl["net"], prior["net"]),
                "cash_balance": round(cash_balance, 2),
                "net_debt": round(net_debt, 2),
                "equity": round(equity, 2),
                "nde_ratio": nde_ratio,
                "nde_target": nde_target,
                "nde_ok": bool(
                    nde_ratio is not None and nde_target is not None
                    and nde_ratio <= nde_target
                ),
                "ebitda_configured": shared["ebitda_configured"],
                "debt_configured": capital["debt_configured"],
                # --- control tower: มิติสภาพคล่อง/เงินทุนหมุนเวียนเพิ่ม ---
                "min_13w": cash_kpis["min_13w"],
                "min_13w_label": cash_kpis["min_13w_label"],
                "min_cash_breach": bool(min_alert["count"]),
                "working_capital": ratio_summary.get("working_capital"),
                "ccc_days": ratio_summary.get("ccc_days"),
            },
            "dimensions": self._overview_dimensions(
                f, shared, tabs, ratio_summary),
            "top_risks": self._top_risks(f, shared),
            "bu_table": bu_table,
        }

    def _ccc_days(self, f, shared, company_id):
        """Cash conversion ต่อบริษัท = DSO + DIO − DPO

        DIO มาจาก _build_inventory (ตามแหล่งข้อมูลของบริษัทนั้น) — ถ้ายังไม่มี
        ข้อมูลสต๊อกจะเหลือ DSO − DPO แบบ v1 เดิมทุกประการ"""
        ar = self._sum_type_co(shared, "bal_cum", (AR_TYPE,), company_id)
        ap = -self._sum_type_co(shared, "bal_cum", (AP_TYPE,), company_id)
        pl = shared["pl_t12m"]["by_company"].get(company_id, {})
        revenue = pl.get("revenue", 0.0)
        spend = pl.get("cogs", 0.0) + pl.get("opex", 0.0)
        dso = ar / revenue * 365.0 if revenue else 0.0
        dpo = ap / spend * 365.0 if spend else 0.0
        dio = (shared.get("dio_by_company") or {}).get(company_id)
        return int(round(dso + (dio or 0.0) - dpo))

    # ------------------------------------------------------------------
    # Inventory & Financial Ratios
    # (แหล่งข้อมูลเลือกต่อบริษัทใน config: Odoo หรือ External Figures —
    #  ตัวเลขที่คำนวณไม่ได้เป็น None เสมอ ห้ามปลอมเป็น 0)
    # ------------------------------------------------------------------
    @staticmethod
    def _drill_partner(key):
        """คีย์ลบ = คู่ค้าภายนอกที่ไม่ได้ผูก res.partner — ไม่มีเอกสารใน Odoo
        ให้เปิดต่อ ส่ง 0 ออกไปแทนเพื่อให้ client ปิดลิงก์ drill ของแถวนั้น"""
        return key if key > 0 else 0

    @staticmethod
    def _cfg_source(cfg_map, company_id, field):
        """แหล่งข้อมูลของบริษัทตาม config — ไม่มี config = Odoo (ค่าตั้งต้น)"""
        cfg = cfg_map.get(company_id)
        return getattr(cfg, field) if cfg else "odoo"

    def _inv_source(self, shared, company_id):
        cfg = shared["cfg_map"].get(company_id)
        return cfg.inventory_source if cfg else "odoo"

    def _invoice_source(self, shared, company_id):
        return self._cfg_source(shared["cfg_map"], company_id, "invoice_source")

    def _invoice_source_group(self, f, shared):
        """แหล่งใบแจ้งหนี้ของทั้งกลุ่มที่เลือกดู — odoo / external / mixed"""
        sources = {
            cid: self._invoice_source(shared, cid) for cid in f["cids"]
        }
        return self._mixed_source(sources) if sources else "odoo"

    def _budget_source(self, shared, company_id):
        return self._cfg_source(shared["cfg_map"], company_id, "budget_source")

    def _ratio_source(self, shared, company_id):
        cfg = shared["cfg_map"].get(company_id)
        return cfg.ratio_source if cfg else "odoo"

    @staticmethod
    def _mixed_source(sources):
        distinct = set(sources.values())
        return distinct.pop() if len(distinct) == 1 else "mixed"

    def _ext_rows(self, cids, kind, upto):
        """แถว External Figures ดิบ (สกุลบริษัท) ของ kind ถึงวันที่ upto
        เรียงตามวันที่ — ใช้ทำ snapshot ณ วันใดก็ได้ ≤ upto ใน Python"""
        if not cids:
            return []
        return self.env["biz.smart.finance.ext.fact"].search_read(
            [("company_id", "in", cids), ("kind", "=", kind),
             ("date", "<=", str(upto))],
            ["company_id", "date", "metric_key", "label", "amount", "qty"],
            order="date, id",
        )

    @staticmethod
    def _ext_snapshot(rows, company_id, at_date):
        """{(metric_key, label): row} — แถวล่าสุดของแต่ละ key ที่ date <= at_date
        (rows เรียงตามวันที่แล้ว — ตัวหลังทับตัวหน้า = ล่าสุดชนะ)"""
        snap = {}
        for row in rows:
            if row["company_id"][0] != company_id or row["date"] > at_date:
                continue
            snap[(row["metric_key"], row["label"] or "")] = row
        return snap

    def _svl_date_domain(self, operator, bound):
        """SVL ไม่มีฟิลด์วันที่ — ใช้วันของ move และ fallback create_date สำหรับ
        ชั้นที่ไม่มี move (ปรับต้นทุน/landed cost ซึ่ง dotted path จับไม่ได้)
        กติกาเดียวกับ biz_st_stock_card._svl_date_domain"""
        return [
            "|",
            "&", ("stock_move_id", "!=", False),
            ("stock_move_id.date", operator, bound),
            "&", ("stock_move_id", "=", False),
            ("create_date", operator, bound),
        ]

    def _svl_read(self, cids, date_from, date_to, rates, by_product=False):
        """มูลค่า SVL สะสม/ช่วง — {company_id: {"value","qty"}} แปลงสกุลแล้ว

        by_product=True → คืน (per_company, per_product) เพิ่มรายสินค้า
        (สินค้า share ข้ามบริษัทได้ — แปลงสกุลก่อนรวมเสมอ)
        ห้ามแตะ unit_cost (group_operator=None) — ต้นทุนเฉลี่ย = value/qty"""
        domain = [("company_id", "in", cids)]
        if date_from:
            domain += self._svl_date_domain(
                ">=", self._utc_bounds(date_from, date_from)[0])
        domain += self._svl_date_domain(
            "<=", self._utc_bounds(date_to, date_to)[1])
        groupby = ["company_id", "product_id"] if by_product else ["company_id"]
        rows = self.env["stock.valuation.layer"]._read_group(
            domain, groupby=groupby, aggregates=["value:sum", "quantity:sum"])
        per_company = defaultdict(lambda: {"value": 0.0, "qty": 0.0})
        per_product = {}
        for row in rows:
            if by_product:
                company, product, value, qty = row
            else:
                company, value, qty = row
                product = None
            rate = rates.get(company.id, 1.0)
            per_company[company.id]["value"] += (value or 0.0) * rate
            per_company[company.id]["qty"] += qty or 0.0
            if product:
                agg = per_product.setdefault(
                    product.id, {"value": 0.0, "qty": 0.0})
                agg["value"] += (value or 0.0) * rate
                agg["qty"] += qty or 0.0
        return (dict(per_company), per_product) if by_product \
            else dict(per_company)

    # เพดานแถว SVL ที่ยอมดูดขึ้นมา bucket ใน Python — เกินกว่านี้ถือว่าคิวรี
    # aggregate ต่องวดแบบเดิมคุ้มกว่า (แลกจำนวนคิวรีกับหน่วยความจำ)
    SVL_TREND_ROW_CAP = 200000

    def _local_date(self, value):
        """datetime (naive UTC จาก DB) -> วันที่ตามโซนเวลาผู้ใช้

        ต้องใช้โซนเดียวกับ `_utc_bounds` ที่ประกอบขอบเขตคิวรี ไม่งั้นแถวที่ตก
        ขอบวัน (เย็นวันสุดท้ายของงวด) จะไปลงงวดผิด"""
        tz = pytz.timezone(self.env.user.tz or "Asia/Bangkok")
        return pytz.utc.localize(value).astimezone(tz).date()

    def _svl_period_deltas(self, cids, periods, rates):
        """[ยอดเคลื่อนไหว SVL ต่องวด] แปลงสกุลแล้ว — อ่านแถวครั้งเดียวแล้ว
        bucket ใน Python แทนการยิง aggregate หนึ่งครั้ง**ต่องวด**
        (เดิม 12-13 คิวรีต่อปีงบ × 2 ปีงบ)

        SVL ไม่มีฟิลด์วันที่จึง groupby รายเดือนไม่ได้ (กติกาเดียวกับ
        `_svl_date_domain`) — ต้องอ่าน `stock_move_id.date` และ fallback
        `create_date` มาแยกงวดเอง
        คืน None = แถวเยอะเกินเพดาน ให้ผู้เรียกกลับไปใช้ทางเดิม"""
        if not cids or not periods:
            return [0.0] * len(periods)
        lo, hi = periods[0]["date_from"], periods[-1]["date_to"]
        dt_lo = self._utc_bounds(lo, lo)[0]
        dt_hi = self._utc_bounds(hi, hi)[1]
        SVL = self.env["stock.valuation.layer"]
        cap = self.SVL_TREND_ROW_CAP
        moved = SVL.search_read(
            [("company_id", "in", cids), ("stock_move_id", "!=", False),
             ("stock_move_id.date", ">=", dt_lo),
             ("stock_move_id.date", "<=", dt_hi)],
            ["company_id", "stock_move_id", "value"], limit=cap + 1)
        if len(moved) > cap:
            return None
        orphan = SVL.search_read(
            [("company_id", "in", cids), ("stock_move_id", "=", False),
             ("create_date", ">=", dt_lo), ("create_date", "<=", dt_hi)],
            ["company_id", "create_date", "value"],
            limit=cap + 1 - len(moved))
        if len(moved) + len(orphan) > cap:
            return None

        move_date = {}
        move_ids = list({row["stock_move_id"][0] for row in moved})
        if move_ids:
            move_date = {
                row["id"]: row["date"]
                for row in self.env["stock.move"].search_read(
                    [("id", "in", move_ids)], ["date"])
            }
        # ปลายงวดเรียงจากน้อยไปมากอยู่แล้ว (งวดต่อเนื่องกัน) — bisect หา
        # งวดแรกที่ปลายงวด >= วันของแถว
        ends = [p["date_to"] for p in periods]
        deltas = [0.0] * len(periods)

        def add(company_pair, day, value):
            if day is None or day < lo or day > hi:
                return
            index = bisect.bisect_left(ends, day)
            if index >= len(ends):
                return
            deltas[index] += (value or 0.0) * rates.get(
                company_pair[0], 1.0)

        for row in moved:
            raw = move_date.get(row["stock_move_id"][0])
            add(row["company_id"],
                self._local_date(raw) if raw else None, row["value"])
        for row in orphan:
            add(row["company_id"],
                self._local_date(row["create_date"]), row["value"])
        return deltas

    @staticmethod
    def _avg_pair(a, b):
        """ค่าเฉลี่ยแบบ None-aware — รู้ข้างเดียวใช้ข้างนั้น ไม่รู้เลย = None"""
        if a is None:
            return b
        if b is None:
            return a
        return (a + b) / 2.0

    def _annualize(self, value, days):
        """ประมาณ trailing 12 เดือนจากยอดสะสม YTD (ต้นปีงบจะหยาบ — จึงมี
        metric *_t12m ให้ระบบภายนอก override ได้)"""
        if value is None or not days:
            return None
        return value * 365.0 / days

    def _build_inventory(self, f, shared):
        """แท็บ Inventory + เขียน DIO/มูลค่าสต๊อกลง shared ให้ Overview/Ratios

        แหล่ง odoo: stock.valuation.layer (มีหมวด/สินค้า/แนวโน้ม) กระทบยอดกับ
        ยอด GL ของบัญชีที่ map ไว้; ไม่มีโมดูล stock → ยอด GL ล้วน (ไม่มีรายละเอียด)
        แหล่ง external: แถว kind=inventory ใน External Figures (หมวด = label)"""
        cids = f["cids"]
        odoo_cids = [c for c in cids if self._inv_source(shared, c) == "odoo"]
        ext_cids = [c for c in cids if c not in odoo_cids]
        svl_ok = "stock.valuation.layer" in self.env
        cfg_map = shared["cfg_map"]

        inv_now, inv_prior = {}, {}
        inv_now_open, inv_prior_open = {}, {}
        by_category = {}
        top_products = []
        trend_now, trend_prior = defaultdict(float), defaultdict(float)
        periods = self._fy_periods(f["fy_start"], f["as_of"])
        periods_prior = self._fy_periods(f["fy_start_prior"], f["as_of_prior"])
        gl_value = recon_diff = None
        recon_ok = recon_shown = False
        inv_account_ids = sorted({
            aid for cfg in cfg_map.values()
            for aid in cfg.inventory_account_ids.ids
        })

        def add_category(name, value, qty, categ_id=None):
            bucket = by_category.setdefault(
                name or _("ไม่ระบุหมวด"),
                {"value": 0.0, "qty": 0.0, "categ_id": categ_id})
            bucket["value"] += value
            bucket["qty"] += qty
            bucket["categ_id"] = bucket["categ_id"] or categ_id

        def gl_sum(key, account_ids, company_id=None):
            return sum(
                bal for aid, bal in shared[key].items()
                if aid in account_ids
                and (company_id is None
                     or shared["acc_company"].get(aid) == company_id)
            )

        # ---- แหล่ง Odoo ----
        if odoo_cids and svl_ok:
            now_c, now_p = self._svl_read(
                odoo_cids, False, f["as_of"], shared["fx"], by_product=True)
            prior_c = self._svl_read(
                odoo_cids, False, f["as_of_prior"], shared["fx_prior"])
            open_c = self._svl_read(
                odoo_cids, False, f["t12m_start"], shared["fx"])
            prior_open_c = self._svl_read(
                odoo_cids, False, f["as_of_prior"] - timedelta(days=364),
                shared["fx_prior"])
            for cid in odoo_cids:
                inv_now[cid] = now_c.get(cid, {}).get("value", 0.0)
                inv_prior[cid] = prior_c.get(cid, {}).get("value", 0.0)
                inv_now_open[cid] = open_c.get(cid, {}).get("value", 0.0)
                inv_prior_open[cid] = prior_open_c.get(cid, {}).get("value", 0.0)

            # หมวด/สินค้า — map categ ใน Python (dotted groupby ใช้ไม่ได้)
            products = self.env["product.product"].search_read(
                [("id", "in", list(now_p))],
                ["default_code", "name", "categ_id"])
            categ_of = {p["id"]: p["categ_id"] for p in products}
            info_of = {p["id"]: p for p in products}
            for product_id, agg in now_p.items():
                categ = categ_of.get(product_id)
                add_category(categ[1] if categ else "", agg["value"],
                             agg["qty"], categ[0] if categ else None)
            ranked = sorted(
                now_p.items(), key=lambda kv: -abs(kv[1]["value"]))[:15]
            for product_id, agg in ranked:
                info = info_of.get(product_id, {})
                top_products.append({
                    "product_id": product_id,
                    "code": info.get("default_code") or "",
                    "name": info.get("name") or "",
                    "qty": round(agg["qty"], 2),
                    "value": round(agg["value"], 2),
                    "avg_cost": round(agg["value"] / agg["qty"], 2)
                    if agg["qty"] else None,
                })

            # แนวโน้มรายงวด = ยอดยกมา + delta สะสมต่องวด (คิวรี aggregate
            # ต่องวด ถูกกว่าดูดแถว SVL ทั้งปีขึ้นมาไล่เอง)
            def svl_trend(period_list, fy_start, rates):
                opening = sum(
                    v["value"] for v in self._svl_read(
                        odoo_cids, False, fy_start - timedelta(days=1), rates
                    ).values())
                deltas = self._svl_period_deltas(
                    odoo_cids, period_list, rates)
                if deltas is None:
                    # ข้อมูลเยอะเกินเพดาน — กลับไปยิง aggregate ต่องวด
                    deltas = [
                        sum(v["value"] for v in self._svl_read(
                            odoo_cids, period["date_from"], period["date_to"],
                            rates).values())
                        for period in period_list
                    ]
                running, points = opening, []
                for delta in deltas:
                    running += delta
                    points.append(running)
                return points
            for index, point in enumerate(
                    svl_trend(periods, f["fy_start"], shared["fx"])):
                trend_now[index] += point
            for index, point in enumerate(
                    svl_trend(periods_prior, f["fy_start_prior"],
                              shared["fx_prior"])):
                trend_prior[index] += point

            # กระทบยอด SVL ↔ GL เฉพาะบริษัทที่ map บัญชีสต๊อกไว้
            mapped = [
                cid for cid in odoo_cids
                if cfg_map.get(cid) and cfg_map[cid].inventory_account_ids
            ]
            if mapped:
                mapped_ids = {
                    aid for cid in mapped
                    for aid in cfg_map[cid].inventory_account_ids.ids
                }
                gl_value = gl_sum("bal_cum", mapped_ids)
                svl_mapped = sum(inv_now.get(cid) or 0.0 for cid in mapped)
                recon_diff = svl_mapped - gl_value
                recon_ok = abs(recon_diff) < max(1000.0, abs(gl_value) * 0.01)
                recon_shown = True
        elif odoo_cids:
            # ไม่มีโมดูล stock — headline จากยอด GL (ไม่มีหมวด/สินค้า/แนวโน้ม)
            for cid in odoo_cids:
                cfg = cfg_map.get(cid)
                ids = set(cfg.inventory_account_ids.ids) if cfg else set()
                inv_now[cid] = gl_sum("bal_cum", ids, cid) if ids else None
                inv_prior[cid] = gl_sum("bal_cum_prior", ids, cid) if ids else None
                inv_now_open[cid] = inv_prior_open[cid] = None

        # ---- แหล่ง external ----
        ext_rows = self._ext_rows(ext_cids, "inventory", f["as_of"])
        for cid in ext_cids:
            rate_now = shared["fx"].get(cid, 1.0)
            rate_prior = shared["fx_prior"].get(cid, 1.0)
            snap = self._ext_snapshot(ext_rows, cid, f["as_of"])
            if snap:
                inv_now[cid] = sum(
                    r["amount"] for r in snap.values()) * rate_now
                for row in snap.values():
                    add_category(row["label"],
                                 row["amount"] * rate_now, row["qty"] or 0.0)
            else:
                inv_now[cid] = None
            snap_prior = self._ext_snapshot(ext_rows, cid, f["as_of_prior"])
            inv_prior[cid] = sum(
                r["amount"] for r in snap_prior.values()) * rate_prior \
                if snap_prior else None
            snap_open = self._ext_snapshot(
                ext_rows, cid, f["t12m_start"])
            inv_now_open[cid] = sum(
                r["amount"] for r in snap_open.values()) * rate_now \
                if snap_open else None
            snap_prior_open = self._ext_snapshot(
                ext_rows, cid, f["as_of_prior"] - timedelta(days=364))
            inv_prior_open[cid] = sum(
                r["amount"] for r in snap_prior_open.values()) * rate_prior \
                if snap_prior_open else None
            for index, period in enumerate(periods):
                point = self._ext_snapshot(ext_rows, cid, period["date_to"])
                trend_now[index] += sum(
                    r["amount"] for r in point.values()) * rate_now
            for index, period in enumerate(periods_prior):
                point = self._ext_snapshot(ext_rows, cid, period["date_to"])
                trend_prior[index] += sum(
                    r["amount"] for r in point.values()) * rate_prior

        # ---- turnover / DIO ต่อบริษัท ----
        # COGS: ตามแหล่ง ratio ของบริษัทนั้น (external ใช้ metric ภายนอก)
        ratio_ext_cids = [
            c for c in cids if self._ratio_source(shared, c) == "external"]
        ratio_rows = self._ext_rows(ratio_ext_cids, "ratio_input", f["as_of"])
        shared["ext_ratio_rows"] = ratio_rows
        days_now = (f["as_of"] - f["fy_start"]).days + 1

        def company_cogs_t12m(cid):
            if cid in ratio_ext_cids:
                snap = self._ext_snapshot(ratio_rows, cid, f["as_of"])
                rate = shared["fx"].get(cid, 1.0)
                row = snap.get(("cogs_t12m", ""))
                if row:
                    return row["amount"] * rate
                row = snap.get(("cogs_ytd", ""))
                return self._annualize(
                    row["amount"] * rate if row else None, days_now)
            return shared["pl_t12m"]["by_company"].get(cid, {}).get("cogs")

        dio_by_company, by_company = {}, {}
        for cid in cids:
            cogs = company_cogs_t12m(cid)
            avg_inv = self._avg_pair(inv_now.get(cid), inv_now_open.get(cid))
            turnover = cogs / avg_inv if cogs and avg_inv else None
            dio = 365.0 / turnover if turnover and turnover > 0 else None
            dio_by_company[cid] = dio
            by_company[cid] = {"turnover": turnover, "dio": dio, "cogs": cogs,
                               "avg_inv": avg_inv}
        shared["dio_by_company"] = dio_by_company
        shared["inventory_values"] = {
            "now": inv_now, "prior": inv_prior,
            "now_open": inv_now_open, "prior_open": inv_prior_open,
        }

        # ---- รวมกลุ่ม + payload ----
        def total(values):
            known = [v for v in values.values() if v is not None]
            return sum(known) if known else None
        total_now, total_prior = total(inv_now), total(inv_prior)
        group_cogs = sum(
            row["cogs"] for row in by_company.values()
            if row["cogs"] and row["avg_inv"])
        group_avg = sum(
            row["avg_inv"] for row in by_company.values()
            if row["cogs"] and row["avg_inv"])
        group_turnover = group_cogs / group_avg if group_avg else None
        group_dio = 365.0 / group_turnover \
            if group_turnover and group_turnover > 0 else None
        shared["inventory_group"] = {
            "turnover": group_turnover, "dio": group_dio}

        sources = {cid: self._inv_source(shared, cid) for cid in cids}
        companies = self.env["res.company"].browse(cids)
        total_categ = sum(
            b["value"] for b in by_category.values()) or 0.0
        return {
            "source": self._mixed_source(sources),
            "source_by_company": {str(k): v for k, v in sources.items()},
            "stock_available": svl_ok,
            "trend_available": bool(trend_now),
            "kpis": {
                "total_value": round(total_now, 2)
                if total_now is not None else None,
                "total_value_prior": round(total_prior, 2)
                if total_prior is not None else None,
                "yoy_pct": self._yoy(total_now, total_prior)
                if total_now is not None and total_prior else None,
                "turnover": round(group_turnover, 2)
                if group_turnover is not None else None,
                "dio_days": int(round(group_dio))
                if group_dio is not None else None,
                "gl_value": round(gl_value, 2)
                if gl_value is not None else None,
                "recon_diff": round(recon_diff, 2)
                if recon_diff is not None else None,
                "recon_ok": recon_ok,
                "recon_shown": recon_shown,
            },
            "by_category": sorted([
                {
                    "name": name,
                    "categ_id": bucket["categ_id"],
                    "value": round(bucket["value"], 2),
                    "qty": round(bucket["qty"], 2),
                    "share_pct": round(
                        bucket["value"] / total_categ * 100.0, 1)
                    if total_categ else 0.0,
                }
                for name, bucket in by_category.items()
            ], key=lambda r: -r["value"]),
            "trend": [
                {
                    "index": period["index"],
                    "label": period["label"],
                    "value": round(trend_now.get(i, 0.0), 2),
                    "value_prior": round(trend_prior[i], 2)
                    if i in trend_prior else None,
                }
                for i, period in enumerate(periods)
            ] if trend_now else [],
            "top_products": top_products,
            "by_company": [
                {
                    "company_id": company.id,
                    "name": company.name,
                    "source": sources[company.id],
                    "value": round(inv_now[company.id], 2)
                    if inv_now.get(company.id) is not None else None,
                    "turnover": round(by_company[company.id]["turnover"], 2)
                    if by_company[company.id]["turnover"] is not None else None,
                    "dio_days": int(round(by_company[company.id]["dio"]))
                    if by_company[company.id]["dio"] is not None else None,
                }
                for company in companies
            ],
            "inventory_account_ids": inv_account_ids,
        }

    def _sum_type_co(self, shared, key, types, company_id):
        index = self._type_index(shared, key)
        return sum(index.get((company_id, atype), 0.0) for atype in types)

    def _equity_co(self, shared, key, company_id):
        """ส่วนของผู้ถือหุ้น ณ balance key = ยอดสะสม (เครดิต) + กำไรที่ยังไม่ปิด
        (คิดจาก PL_TYPES ตรง ๆ — bal_open ย้อนก่อน closing entries ของปีเก่า
        จึงใช้ pl_ytd แบบ overview ไม่ได้)"""
        return (
            -self._sum_type_co(shared, key, EQUITY_TYPES, company_id)
            - self._sum_type_co(shared, key, PL_TYPES, company_id)
        )

    def _ratio_inputs(self, f, shared, company_id, prior=False):
        """ตัวเลขตั้งต้นของบริษัทหนึ่ง หนึ่งคอลัมน์ (inputs-first)

        คืน (inputs dict, missing list) — ค่าที่ไม่รู้เป็น None เพื่อให้ ratio
        ที่ต้องใช้มันเป็น None ตาม ไม่ใช่เพี้ยนเป็น 0"""
        inv_key = "prior" if prior else "now"
        # สต๊อกมีสองบทบาท และคนละฐานวัดกัน:
        #   inventory      = ฐานงบดุล (GL) — ใช้หักใน Quick Ratio เท่านั้น
        #   inventory_ops  = ฐานการเคลื่อนไหว (SVL/ภายนอก) — ใช้ turnover/DIO
        # ห้ามสลับกัน ไม่งั้นจะเอาตัวเลขคนละฐานมาลบกัน (Quick Ratio เพี้ยนหนัก)
        inventory_ops = shared["inventory_values"][inv_key].get(company_id)
        inventory_ops_open = shared["inventory_values"][
            inv_key + "_open"].get(company_id)
        inventory = inventory_open = None
        days = ((f["as_of_prior"] - f["fy_start_prior"]).days + 1) if prior \
            else ((f["as_of"] - f["fy_start"]).days + 1)

        if self._ratio_source(shared, company_id) == "external":
            rows = shared.get("ext_ratio_rows") or []
            rate = (shared["fx_prior"] if prior else shared["fx"]).get(
                company_id, 1.0)
            as_of = f["as_of_prior"] if prior else f["as_of"]
            open_date = (f["fy_start_prior"] if prior else f["fy_start"]) \
                - timedelta(days=1)
            snap = self._ext_snapshot(rows, company_id, as_of)
            snap_open = self._ext_snapshot(rows, company_id, open_date)

            def get(key, source=None):
                row = (source if source is not None else snap).get((key, ""))
                return row["amount"] * rate if row else None

            revenue, cogs = get("revenue_ytd"), get("cogs_ytd")
            gross = get("gross_profit_ytd")
            if gross is None and revenue is not None and cogs is not None:
                gross = revenue - cogs
            net, interest = get("net_profit_ytd"), get("interest_expense_ytd")
            ebit = get("ebit_ytd")
            if ebit is None and net is not None and interest is not None:
                ebit = net + interest
            opex = get("opex_ytd")
            revenue_t12m = get("revenue_t12m")
            if revenue_t12m is None:
                revenue_t12m = self._annualize(revenue, days)
            cogs_t12m = get("cogs_t12m")
            if cogs_t12m is None:
                cogs_t12m = self._annualize(cogs, days)
            spend_t12m = None
            if cogs_t12m is not None:
                spend_t12m = cogs_t12m + (
                    self._annualize(opex, days) or 0.0)
            inputs = {
                "cash": get("cash_and_equivalents"),
                "ar": get("accounts_receivable"),
                # ภายนอกส่งงบชุดเดียว ทั้งสองบทบาทจึงเป็นตัวเลขเดียวกัน:
                # metric inventory_value ถ้ามี ไม่งั้นใช้ยอดรวมรายหมวด
                # (kind=inventory) ที่แท็บ Inventory รวมไว้แล้ว
                "inventory": get("inventory_value")
                if get("inventory_value") is not None else inventory_ops,
                "inventory_ops": inventory_ops
                if inventory_ops is not None else get("inventory_value"),
                "inventory_ops_open": inventory_ops_open,
                "current_assets": get("current_assets"),
                "total_assets": get("total_assets"),
                "total_assets_open": get("total_assets", snap_open),
                "ap": get("accounts_payable"),
                "current_liabilities": get("current_liabilities"),
                "total_liabilities": get("total_liabilities"),
                "total_debt": get("total_debt"),
                "equity": get("equity"),
                "equity_open": get("equity", snap_open),
                "revenue": revenue, "cogs": cogs, "gross": gross,
                "net": net, "interest": interest, "ebit": ebit,
                "revenue_t12m": revenue_t12m, "cogs_t12m": cogs_t12m,
                "spend_t12m": spend_t12m,
            }
            missing = sorted(
                key for key in EXT_CORE_KEYS if (key, "") not in snap)
            return inputs, missing

        # ---- แหล่ง Odoo (จาก balance ที่ _build_shared เตรียมไว้แล้ว) ----
        col = "bal_cum_prior" if prior else "bal_cum"
        open_key = "bal_open_prior" if prior else "bal_open"
        pl = shared["pl_prior" if prior else "pl_ytd"]["by_company"].get(
            company_id, {})
        if prior:
            t12m = {
                key: self._annualize(pl.get(key, 0.0), days)
                for key in ("revenue", "cogs", "opex")
            }
        else:
            t12m = shared["pl_t12m"]["by_company"].get(
                company_id, {"revenue": 0.0, "cogs": 0.0, "opex": 0.0})
        cfg = shared["cfg_map"].get(company_id)
        # สต๊อกสำหรับอัตราส่วนต้องมาจากฐานเดียวกับสินทรัพย์หมุนเวียน (GL)
        # ถ้า map บัญชีไว้ — เอา SVL ไปลบยอด GL คือผสมฐานวัด Quick Ratio จะเพี้ยน
        # (ส่วนต่างสองฐานไปโชว์เป็น badge กระทบยอดในแท็บ Inventory แทน)
        # เซ็ตต่อบริษัท (Odoo M2M ∪ ธงบัญชีภายนอก) เตรียมไว้แล้วใน _build_shared
        inv_ids = shared["inv_ids_by_company"].get(company_id, set())
        if inv_ids:
            inventory = sum(
                bal for aid, bal in shared[col].items()
                if aid in inv_ids
                and shared["acc_company"].get(aid) == company_id
            )
            inventory_open = sum(
                bal for aid, bal in shared[open_key].items()
                if aid in inv_ids
                and shared["acc_company"].get(aid) == company_id
            )
        debt_ids = shared["debt_ids_by_company"].get(company_id, set())
        total_debt = -sum(
            shared[col].get(aid, 0.0) for aid in debt_ids
            if shared["acc_company"].get(aid) == company_id
        ) if debt_ids else None
        net = pl.get("net", 0.0)
        interest = pl.get("interest", 0.0)
        inputs = {
            "cash": self._sum_type_co(shared, col, ("asset_cash",), company_id),
            "ar": self._sum_type_co(shared, col, (AR_TYPE,), company_id),
            "inventory": inventory,
            "inventory_ops": inventory_ops,
            "inventory_ops_open": inventory_ops_open,
            "current_assets": self._sum_type_co(
                shared, col, CA_TYPES, company_id),
            "total_assets": self._sum_type_co(
                shared, col, ASSET_TYPES, company_id),
            "total_assets_open": self._sum_type_co(
                shared, open_key, ASSET_TYPES, company_id),
            "ap": -self._sum_type_co(shared, col, (AP_TYPE,), company_id),
            "current_liabilities": -self._sum_type_co(
                shared, col, CL_TYPES, company_id),
            "total_liabilities": -self._sum_type_co(
                shared, col, LIAB_TYPES, company_id),
            "total_debt": total_debt,
            "equity": self._equity_co(shared, col, company_id),
            "equity_open": self._equity_co(shared, open_key, company_id),
            "revenue": pl.get("revenue", 0.0),
            "cogs": pl.get("cogs", 0.0),
            "gross": pl.get("gross", 0.0),
            "net": net,
            "interest": interest,
            # EBIT = net + ดอกเบี้ย + ภาษี (จากบัญชีที่ map ไว้)
            "ebit": net + interest + pl.get("tax", 0.0),
            "revenue_t12m": t12m.get("revenue") or 0.0,
            "cogs_t12m": t12m.get("cogs") or 0.0,
            "spend_t12m": (t12m.get("cogs") or 0.0) + (t12m.get("opex") or 0.0),
        }
        return inputs, []

    RATIO_GROUPS = [
        ("liquidity", "สภาพคล่อง", [
            ("current_ratio", "Current Ratio", "x"),
            ("quick_ratio", "Quick Ratio", "x"),
        ]),
        ("leverage", "หนี้สิน", [
            ("debt_to_equity", "Debt to Equity", "x"),
            ("interest_coverage", "Interest Coverage", "x"),
        ]),
        ("profitability", "ความสามารถทำกำไร", [
            ("gross_margin_pct", "Gross Profit Margin", "pct"),
            ("net_margin_pct", "Net Profit Margin", "pct"),
            ("roa_pct", "ROA (annualized)", "pct"),
            ("roe_pct", "ROE (annualized)", "pct"),
        ]),
        ("efficiency", "ประสิทธิภาพ", [
            ("inventory_turnover", "Inventory Turnover", "x"),
            ("dio_days", "Days of Inventory (DIO)", "days"),
            ("dso_days", "Days Sales Outstanding (DSO)", "days"),
            ("dpo_days", "Days Payable Outstanding (DPO)", "days"),
            ("asset_turnover", "Asset Turnover", "x"),
            ("ccc_days", "Cash Conversion Cycle", "days"),
        ]),
    ]

    def _ratio_values(self, g, days):
        """คำนวณอัตราส่วนทุกตัวจาก inputs dict หนึ่งคอลัมน์ — คืน
        (values, flags) ค่าที่คำนวณไม่ได้เป็น None เสมอ ไม่ปลอมเป็น 0

        ตัวหารต้องเป็นบวกเท่านั้น: หนี้สินหมุนเวียน/ส่วนของผู้ถือหุ้น/รายได้
        ที่ติดลบทำให้อัตราส่วนพลิกเครื่องหมายจนอ่านว่า "ดี" ทั้งที่กิจการมีปัญหา
        (เจอจริงในข้อมูล dev: CA และ CL ติดลบทั้งคู่ → current 0.74, quick 302)
        กรณีนี้จึงคืน None พร้อมธง neg_base ให้จอบอกเหตุผลแทนการโชว์ตัวเลขลวง"""
        flags = defaultdict(list)

        def div(a, b, key=None):
            if a is None or b is None or b == 0:
                return None
            if b < 0:
                if key:
                    flags[key].append("neg_base")
                return None
            return a / b

        ca, cl = g["current_assets"], g["current_liabilities"]
        current = div(ca, cl, "current_ratio")
        if g["inventory"] is None:
            # ยังไม่ map บัญชีสต๊อก — ห้ามเอามูลค่า SVL (คนละฐาน) มาหักยอด GL
            quick = current
            if current is not None:
                flags["quick_ratio"].append("quick_approx")
        else:
            quick = div(ca - g["inventory"] if ca is not None else None, cl,
                        "quick_ratio")
        debt = g["total_debt"]
        if debt is None and g["total_liabilities"] is not None:
            debt = g["total_liabilities"]
            flags["debt_to_equity"].append("de_approx")
        coverage = div(g["ebit"], g["interest"]) \
            if g["interest"] and g["interest"] > 0 else None
        annual_net = self._annualize(g["net"], days)
        avg_inv = self._avg_pair(g["inventory_ops"], g["inventory_ops_open"])
        # ไม่มี COGS = คำนวณรอบหมุนไม่ได้ (ไม่ใช่ "หมุน 0 รอบ")
        turnover = div(g["cogs_t12m"], avg_inv, "inventory_turnover") \
            if g["cogs_t12m"] else None
        dio = 365.0 / turnover if turnover and turnover > 0 else None
        dso = div((g["ar"] or 0.0) * 365.0 if g["ar"] is not None else None,
                  g["revenue_t12m"], "dso_days")
        dpo = div((g["ap"] or 0.0) * 365.0 if g["ap"] is not None else None,
                  g["spend_t12m"], "dpo_days")
        ccc = None
        if dso is not None and dpo is not None:
            ccc = dso + (dio or 0.0) - dpo
            if dio is None:
                flags["ccc_days"].append("no_dio")
        avg_assets = self._avg_pair(g["total_assets"], g["total_assets_open"])
        values = {
            "current_ratio": current,
            "quick_ratio": quick,
            "debt_to_equity": div(debt, g["equity"], "debt_to_equity"),
            "interest_coverage": coverage,
            "gross_margin_pct": div(g["gross"], g["revenue"],
                                    "gross_margin_pct"),
            "net_margin_pct": div(g["net"], g["revenue"], "net_margin_pct"),
            "roa_pct": div(annual_net, avg_assets, "roa_pct"),
            "roe_pct": div(annual_net, self._avg_pair(
                g["equity"], g["equity_open"]), "roe_pct"),
            "inventory_turnover": turnover,
            "dio_days": dio,
            "dso_days": dso,
            "dpo_days": dpo,
            "asset_turnover": div(g["revenue_t12m"], avg_assets,
                                  "asset_turnover"),
            "ccc_days": ccc,
        }
        for key in ("gross_margin_pct", "net_margin_pct",
                    "roa_pct", "roe_pct"):
            if values[key] is not None:
                values[key] *= 100.0
        return values, flags

    @staticmethod
    def _round_unit(value, unit):
        if value is None:
            return None
        if unit == "days":
            return int(round(value)) or 0  # ตัด -0 ที่เกิดจากการปัด
        rounded = round(value, 1 if unit == "pct" else 2)
        return rounded + 0.0 if rounded else 0.0  # ตัด -0.0

    def _build_ratios(self, f, shared):
        """แท็บ Financial Ratios — inputs-first: รวมตัวเลขตั้งต้นข้ามบริษัท
        (ตามแหล่งของแต่ละบริษัท แปลงสกุลแล้ว) ก่อนค่อยคิดอัตราส่วน
        = ratio ของผลรวม ไม่ใช่ผลรวมของ ratio"""
        cids = f["cids"]
        days_now = (f["as_of"] - f["fy_start"]).days + 1
        days_prior = (f["as_of_prior"] - f["fy_start_prior"]).days + 1

        inputs_by_company = {}
        missing_by_company = []
        for cid in cids:
            inputs_by_company[cid] = {
                "now": self._ratio_inputs(f, shared, cid, prior=False),
                "prior": self._ratio_inputs(f, shared, cid, prior=True),
            }
            missing = inputs_by_company[cid]["now"][1]
            if missing:
                missing_by_company.append({
                    "company_id": cid,
                    "name": shared["company_name"].get(cid, ""),
                    "missing": missing,
                })

        def group_inputs(column):
            total, seen, partial = defaultdict(float), set(), set()
            for cid in cids:
                inputs = inputs_by_company[cid][column][0]
                for name, value in inputs.items():
                    if value is None:
                        partial.add(name)
                    else:
                        total[name] += value
                        seen.add(name)
            g = {name: (total[name] if name in seen else None)
                 for name in inputs_by_company[cids[0]][column][0]}
            return g, partial & seen  # partial = บางบริษัทมี บางบริษัทไม่มี

        g_now, partial_now = group_inputs("now")
        g_prior, _partial_prior = group_inputs("prior")
        values_now, flags_now = self._ratio_values(g_now, days_now)
        values_prior, _flags_prior = self._ratio_values(g_prior, days_prior)

        # input ที่บางบริษัทขาด → ratio ที่ใช้ input นั้นติดธง partial
        USES = {
            "current_ratio": ("current_assets", "current_liabilities"),
            "quick_ratio": ("current_assets", "current_liabilities",
                            "inventory"),
            "debt_to_equity": ("total_debt", "total_liabilities", "equity"),
            "interest_coverage": ("ebit", "interest"),
            "gross_margin_pct": ("gross", "revenue"),
            "net_margin_pct": ("net", "revenue"),
            "roa_pct": ("net", "total_assets"),
            "roe_pct": ("net", "equity"),
            "inventory_turnover": ("cogs_t12m", "inventory_ops"),
            "dio_days": ("cogs_t12m", "inventory_ops"),
            "dso_days": ("ar", "revenue_t12m"),
            "dpo_days": ("ap", "spend_t12m"),
            "asset_turnover": ("revenue_t12m", "total_assets"),
            "ccc_days": ("ar", "ap", "cogs_t12m"),
        }
        groups = []
        for group_key, group_label, rows in self.RATIO_GROUPS:
            out_rows = []
            for key, label, unit in rows:
                value = self._round_unit(values_now.get(key), unit)
                prior = self._round_unit(values_prior.get(key), unit)
                delta = None
                if value is not None and prior is not None:
                    delta = self._round_unit(value - prior, unit)
                row_flags = list(flags_now.get(key, []))
                if partial_now & set(USES.get(key, ())):
                    row_flags.append("partial")
                out_rows.append({
                    "key": key, "label": label, "unit": unit,
                    "value": value, "prior": prior, "delta": delta,
                    "flags": row_flags,
                })
            groups.append({
                "key": group_key, "label": group_label, "rows": out_rows,
            })

        sources = {cid: self._ratio_source(shared, cid) for cid in cids}
        by_company = []
        for company in self.env["res.company"].browse(cids):
            values, _fl = self._ratio_values(
                inputs_by_company[company.id]["now"][0], days_now)
            by_company.append({
                "company_id": company.id,
                "name": company.name,
                "source": sources[company.id],
                "current_ratio": self._round_unit(
                    values["current_ratio"], "x"),
                "debt_to_equity": self._round_unit(
                    values["debt_to_equity"], "x"),
                "net_margin_pct": self._round_unit(
                    values["net_margin_pct"], "pct"),
                "roe_pct": self._round_unit(values["roe_pct"], "pct"),
                "dio_days": self._round_unit(values["dio_days"], "days"),
                "ccc_days": self._round_unit(values["ccc_days"], "days"),
            })
        return {
            "source": self._mixed_source(sources),
            "source_by_company": {str(k): v for k, v in sources.items()},
            "groups": groups,
            "by_company": by_company,
            "missing_by_company": missing_by_company,
            # digest ให้ Overview control tower / AI / exec PWA อ่านค่ากลุ่ม
            # โดยไม่ต้องไล่ groups เอง (ปัดหน่วยตามชนิดเหมือนที่โชว์ในตาราง)
            "summary": {
                "current_ratio": self._round_unit(
                    values_now.get("current_ratio"), "x"),
                "quick_ratio": self._round_unit(
                    values_now.get("quick_ratio"), "x"),
                "debt_to_equity": self._round_unit(
                    values_now.get("debt_to_equity"), "x"),
                "net_margin_pct": self._round_unit(
                    values_now.get("net_margin_pct"), "pct"),
                "roe_pct": self._round_unit(values_now.get("roe_pct"), "pct"),
                "dso_days": self._round_unit(values_now.get("dso_days"), "days"),
                "dio_days": self._round_unit(values_now.get("dio_days"), "days"),
                "dpo_days": self._round_unit(values_now.get("dpo_days"), "days"),
                "ccc_days": self._round_unit(values_now.get("ccc_days"), "days"),
                "working_capital": (
                    round((g_now.get("current_assets") or 0.0)
                          - (g_now.get("current_liabilities") or 0.0), 2)
                    if g_now.get("current_assets") is not None
                    or g_now.get("current_liabilities") is not None
                    else None),
            },
        }

    # ------------------------------------------------------------------
    # Cash & Liquidity
    # ------------------------------------------------------------------
    def _bank_operating_buffer_pct(self, shared):
        """% buffer เหนือเงินสดขั้นต่ำ — ใช้ค่าสูงสุด (เข้มงวดที่สุด) ของ
        บริษัทในขอบเขต ไม่มี config เลยใช้ค่าตั้งต้นของฟิลด์ (10%)"""
        if not shared["cfg_map"]:
            return 10.0
        return max(
            (cfg.operating_buffer_pct or 0.0)
            for cfg in shared["cfg_map"].values())

    def _bank_alloc_history_months(self, shared):
        """ช่วงประวัติ (เดือน) ที่ใช้คิดสัดส่วนกระจายเงินรายธนาคาร"""
        if not shared["cfg_map"]:
            return BANK_ALLOC_HISTORY_DEFAULT
        return max(
            (cfg.bank_alloc_history_months or BANK_ALLOC_HISTORY_DEFAULT)
            for cfg in shared["cfg_map"].values())

    def _split_shares(self, bank_ids, overrides, weights):
        """คืน {bank_id: สัดส่วน 0..1} รวมกัน = 1.0 เสมอ (เมื่อ bank_ids ไม่ว่าง)

        ธนาคารที่ตั้งทับ (overrides > 0) ใช้ค่านั้นตรง ๆ ส่วนที่เหลือกระจาย
        ตาม weights (ประวัติ/ยอดเงินสด) ให้ธนาคารที่ไม่ได้ตั้งทับ — ถ้าตั้งทับ
        รวมกัน >= 100 ให้ normalise เฉพาะกลุ่มที่ตั้งทับลงมาที่ 100 แทน"""
        if not bank_ids:
            return {}
        override_sum = sum(overrides.get(b, 0.0) for b in bank_ids)
        if override_sum <= 0:
            total_w = sum(weights.get(b, 0.0) for b in bank_ids)
            if total_w > 0:
                return {b: weights.get(b, 0.0) / total_w for b in bank_ids}
            even = 1.0 / len(bank_ids)
            return {b: even for b in bank_ids}
        if override_sum >= 100:
            return {b: overrides.get(b, 0.0) / override_sum for b in bank_ids}
        remaining_pct = 100.0 - override_sum
        free_ids = [b for b in bank_ids if not overrides.get(b)]
        shares = {b: overrides.get(b, 0.0) / 100.0 for b in bank_ids}
        if free_ids:
            free_w = sum(weights.get(b, 0.0) for b in free_ids)
            if free_w > 0:
                for b in free_ids:
                    shares[b] += (
                        (remaining_pct / 100.0)
                        * (weights.get(b, 0.0) / free_w))
            else:
                even = (remaining_pct / 100.0) / len(free_ids)
                for b in free_ids:
                    shares[b] += even
        return shares

    def _alloc_with_remainder(self, amount, shares, bank_ids, tie_breaker):
        """กระจาย amount ตาม shares เป็นจำนวนเงินปัด 2 ตำแหน่ง แล้วยัดเศษปัด
        ที่เหลือให้ tie_breaker รับไว้ — รับประกัน Σ ผลลัพธ์ == round(amount, 2)
        เป๊ะ (invariant #2: Cash Position by Bank ต้องบวกกลับเป็นยอดกลุ่ม)"""
        amount = round(amount or 0.0, 2)
        if not bank_ids:
            return {}
        raw = {b: round(amount * shares.get(b, 0.0), 2) for b in bank_ids}
        remainder = round(amount - sum(raw.values()), 2)
        if remainder and tie_breaker in raw:
            raw[tie_breaker] = round(raw[tie_breaker] + remainder, 2)
        return raw

    def _bank_balances(self, f, shared):
        """{bank_id: ยอดเงินสดปัจจุบันแปลงสกุลนำเสนอแล้ว} จาก AML ต่อบัญชี —
        คนละคิวรีกับ bal_cum (ไม่มีการ merge Trial Balance ภายนอก/มิติบัญชี
        ธนาคารในระดับนี้) ผลรวมจึงอาจไม่เท่า forecast.opening เป๊ะ ผู้เรียกต้อง
        ใส่ส่วนต่างเป็นแถว residual เอง (ห้าม rescale ปิดปัญหา)

        ต้องกรองด้วย account_id (ของ journal.default_account_id) ไม่ใช่
        journal_id — ผลรวม balance ของทุกบรรทัดในสมุดรายวันเดียวกันเป็นศูนย์
        เสมอตามหลัก double-entry (ดูหมายเหตุที่ _build_shared)"""
        cids = f["cids"]
        bank_account_ids = shared["bank_account_ids"]
        bank_of_account = shared["bank_of_account"]
        by_bank = defaultdict(float)
        if bank_account_ids:
            domain = [
                ("parent_state", "=", "posted"),
                ("company_id", "in", cids),
                ("account_id", "in", bank_account_ids),
                ("date", "<=", str(f["as_of"])),
            ]
            rows = self.env["account.move.line"]._read_group(
                domain, groupby=["account_id", "company_id"],
                aggregates=["balance:sum"],
            )
            for account, company, bal in rows:
                bank_id = bank_of_account.get(account.id)
                if not bank_id:
                    continue
                by_bank[bank_id] += self._conv(shared, bal or 0.0, company.id)
        return dict(by_bank)

    def _bank_shares(self, f, shared, balances):
        """คืน (receipt_share, payment_share, basis) — สัดส่วนกระจายเงินเข้า/
        ออกรายสัปดาห์ไปแต่ละธนาคาร: ประวัติเดินบัญชีจริงย้อนหลัง N เดือน
        (bank_alloc_history_months) ก่อน, ธนาคารที่ตั้งทับ % เอง (ในฟอร์ม)
        ชนะเสมอสำหรับตัวเอง, ไม่มีประวัติเลยจึงเฉลี่ยตามยอดเงินสดปัจจุบัน,
        ไม่มีอะไรเลยเฉลี่ยเท่ากัน"""
        bank_rows = shared["bank_rows"]
        bank_ids = [row["id"] for row in bank_rows]
        if not bank_ids:
            return {}, {}, "even"
        cids = f["cids"]
        bank_account_ids = shared["bank_account_ids"]
        bank_of_account = shared["bank_of_account"]

        hist_in = defaultdict(float)
        hist_out = defaultdict(float)
        if bank_account_ids:
            months = self._bank_alloc_history_months(shared)
            history_start = f["today"] - relativedelta(months=months)
            # กรองด้วย account_id เหตุผลเดียวกับ _bank_balances — debit/credit
            # แยกกันของ "บัญชีธนาคาร" เท่านั้น ไม่ใช่ทุกบรรทัดในสมุดรายวัน
            domain = [
                ("parent_state", "=", "posted"),
                ("company_id", "in", cids),
                ("account_id", "in", bank_account_ids),
                ("date", ">=", str(history_start)),
                ("date", "<=", str(f["today"])),
            ]
            rows = self.env["account.move.line"]._read_group(
                domain, groupby=["account_id"],
                aggregates=["debit:sum", "credit:sum"],
            )
            for account, debit, credit in rows:
                bank_id = bank_of_account.get(account.id)
                if not bank_id:
                    continue
                hist_in[bank_id] += debit or 0.0
                hist_out[bank_id] += credit or 0.0

        overrides_in = {row["id"]: row["receipt_share_pct"] for row in bank_rows}
        overrides_out = {row["id"]: row["payment_share_pct"] for row in bank_rows}
        balance_weights = {bid: max(bal, 0.0) for bid, bal in balances.items()}

        receipt_weights = hist_in if any(hist_in.values()) else balance_weights
        payment_weights = hist_out if any(hist_out.values()) else balance_weights

        receipt_share = self._split_shares(bank_ids, overrides_in, receipt_weights)
        payment_share = self._split_shares(bank_ids, overrides_out, payment_weights)

        if any(overrides_in.values()) or any(overrides_out.values()):
            basis = "override"
        elif any(hist_in.values()) or any(hist_out.values()):
            basis = "history"
        elif any(balance_weights.values()):
            basis = "balance"
        else:
            basis = "even"
        return receipt_share, payment_share, basis

    def _build_bank_cash(self, f, shared):
        """13 สัปดาห์รายธนาคาร — อ่าน inflow/outflow จาก
        shared["cash_forecast"]["rows"] ที่คำนวณไว้แล้วเท่านั้น (ห้ามคิวรี
        legs ใหม่ ไม่งั้น Cash/Overview/AP/Forecast จะเห็นตัวเลขไม่ตรงกัน)"""
        bank_rows = shared["bank_rows"]
        forecast = shared["cash_forecast"]
        weeks_out = forecast["weeks"]
        if not bank_rows:
            return {
                "configured": False, "shares_basis": "even",
                "weeks": weeks_out, "rows": [], "alerts": [], "residual": 0.0,
            }

        weeks_full = shared["weeks"]  # มี _from/_to (date object) — ใช้ภายในเท่านั้น
        balances = self._bank_balances(f, shared)
        receipt_share, payment_share, basis = self._bank_shares(
            f, shared, balances)

        total_group_opening = forecast["opening"]
        residual_opening = round(
            total_group_opening - sum(balances.values()), 2)

        bank_ids = [row["id"] for row in bank_rows]
        bank_name_map = {row["id"]: row["name"] for row in bank_rows}
        min_balance_map = {
            row["id"]: round(
                self._conv(shared, row["min_balance"], row["company_id"]), 2)
            for row in bank_rows
        }
        receipt_tie = max(bank_ids, key=lambda b: receipt_share.get(b, 0.0))
        payment_tie = max(bank_ids, key=lambda b: payment_share.get(b, 0.0))

        # แผนโอนที่มีผล (draft/approved) ในกริด 13 สัปดาห์ — zero-sum ต่อสัปดาห์
        transfers = self.env["biz.smart.finance.bank.transfer"].search([
            ("company_id", "in", f["cids"]),
            ("state", "in", ("draft", "approved")),
            ("execution_date", ">=", weeks_full[0]["date_from"]),
            ("execution_date", "<=", weeks_full[-1]["date_to"]),
        ])
        n = len(weeks_full)
        transfer_net = {bid: [0.0] * n for bid in bank_ids}
        for tr in transfers:
            idx = self._week_index(weeks_full, tr.execution_date)
            if idx is None:
                continue
            amount = self._conv(shared, tr.amount, tr.company_id.id)
            if tr.source_bank_id.id in transfer_net:
                transfer_net[tr.source_bank_id.id][idx] -= amount
            if tr.dest_bank_id.id in transfer_net:
                transfer_net[tr.dest_bank_id.id][idx] += amount

        running = dict(balances)
        for bid in bank_ids:
            running.setdefault(bid, 0.0)
        bank_weeks = {bid: [] for bid in bank_ids}
        alerts = []
        for i, week in enumerate(weeks_out):
            fc_row = forecast["rows"][i]
            inflow = fc_row["inflow_collections"] + fc_row["inflow_other"]
            outflow = (fc_row["outflow_ap"] + fc_row["outflow_payroll_opex"]
                       + fc_row["outflow_tax_other"])
            receipts = self._alloc_with_remainder(
                inflow, receipt_share, bank_ids, receipt_tie)
            payments = self._alloc_with_remainder(
                outflow, payment_share, bank_ids, payment_tie)
            for bid in bank_ids:
                row_opening = running[bid]
                net_transfer = round(transfer_net[bid][i], 2)
                ending = round(
                    row_opening + receipts[bid] - payments[bid]
                    + net_transfer, 2)
                running[bid] = ending
                min_bal = min_balance_map.get(bid) or 0.0
                below = bool(min_bal and ending < min_bal)
                bank_weeks[bid].append({
                    "opening": round(row_opening, 2),
                    "receipts": receipts[bid],
                    "payments": payments[bid],
                    "transfer_net": net_transfer,
                    "ending": ending,
                    "below_min": below,
                })
                if below:
                    alerts.append({
                        "bank_id": bid,
                        "bank_name": bank_name_map.get(bid, ""),
                        "week_index": i,
                        "label": week["label"],
                        "projected": ending,
                        "min_balance": min_bal,
                        "gap": round(min_bal - ending, 2),
                    })

        # สถานะรายธนาคาร (สำหรับตาราง Bank Balance by Bank) — at_risk ถ้ามี
        # สัปดาห์ไหนหลุดขั้นต่ำ, monitor ถ้าปลายช่วงยังไม่หลุดแต่ต่ำกว่า
        # operating buffer, ไม่งั้น on_track
        buffer_pct = self._bank_operating_buffer_pct(shared)

        def bank_status(bid):
            weeks_data = bank_weeks[bid]
            if any(w["below_min"] for w in weeks_data):
                return "at_risk"
            min_bal = min_balance_map.get(bid) or 0.0
            last_ending = weeks_data[-1]["ending"] if weeks_data else 0.0
            if min_bal and last_ending < min_bal * (1.0 + buffer_pct / 100.0):
                return "monitor"
            return "on_track"

        rows = [{
            "bank_id": bid,
            "name": bank_name_map.get(bid, ""),
            "min_balance": min_balance_map.get(bid) or 0.0,
            "current_balance": round(balances.get(bid, 0.0), 2),
            "status": bank_status(bid),
            "weeks": bank_weeks[bid],
        } for bid in bank_ids]

        if abs(residual_opening) >= 0.01:
            residual_weeks = [{
                "opening": residual_opening, "receipts": 0.0, "payments": 0.0,
                "transfer_net": 0.0, "ending": residual_opening,
                "below_min": False,
            } for _ in weeks_out]
            rows.append({
                "bank_id": 0,
                "name": _("ไม่ผูกธนาคาร / ปรับปรุง TB ภายนอก"),
                "min_balance": 0.0,
                "current_balance": residual_opening,
                "status": "on_track",
                "weeks": residual_weeks,
            })

        return {
            "configured": True,
            "shares_basis": basis,
            "weeks": weeks_out,
            "rows": rows,
            "alerts": alerts,
            "residual": residual_opening,
        }

    def _build_facilities(self, f, shared):
        """วงเงินสินเชื่อ/OD ต่อธนาคาร — drawn จาก GL (บัญชีที่ map ไว้) หรือ
        กรอกมือ ตามที่ตั้งไว้ที่วงเงินแต่ละใบ"""
        bank_name_map = {row["id"]: row["name"] for row in shared["bank_rows"]}
        facilities = self.env["biz.smart.finance.bank.facility"].search(
            [("company_id", "in", f["cids"])],
            order="bank_id, sequence, id")
        rows = []
        total_limit = total_drawn = cash_limit = cash_available = restricted_limit = 0.0
        for fac in facilities:
            company_id = fac.company_id.id
            limit = self._conv(shared, fac.credit_limit, company_id)
            if fac.drawn_basis == "gl":
                drawn = sum(
                    abs(shared["bal_cum"].get(acc_id, 0.0))
                    for acc_id in fac.drawn_account_ids.ids)
            else:
                drawn = self._conv(shared, fac.drawn_amount, company_id)
            available = limit - drawn
            expired = bool(fac.expiry_date and fac.expiry_date < f["today"])
            cash_drawable = fac.facility_type in ("od", "revolving", "term_loan", "lc_tr") and not expired
            utilisation_pct = (
                round(drawn / limit * 100.0, 1) if limit else 0.0)
            if utilisation_pct >= FACILITY_UTIL_RISK:
                status = "risk"
            elif utilisation_pct >= FACILITY_UTIL_MONITOR:
                status = "monitor"
            else:
                status = "healthy"
            rows.append({
                "id": fac.id,
                "bank_id": fac.bank_id.id,
                "bank_name": bank_name_map.get(fac.bank_id.id, fac.bank_id.name),
                "name": fac.name,
                "facility_type": fac.facility_type,
                "credit_limit": round(limit, 2),
                "drawn": round(drawn, 2),
                "available": round(available, 2),
                "cash_available": round(max(available, 0.0) if cash_drawable else 0.0, 2),
                "expired": expired,
                "cash_drawable": cash_drawable,
                "utilisation_pct": utilisation_pct,
                "status": status,
            })
            total_limit += limit
            total_drawn += drawn
            if cash_drawable:
                cash_limit += limit
                cash_available += max(available, 0.0)
            else:
                restricted_limit += limit
        total_available = total_limit - total_drawn
        total_util = (
            round(total_drawn / total_limit * 100.0, 1) if total_limit else 0.0)
        return {
            "rows": rows,
            "total": {
                "credit_limit": round(total_limit, 2),
                "drawn": round(total_drawn, 2),
                "available": round(total_available, 2),
                "cash_credit_limit": round(cash_limit, 2),
                "cash_available": round(cash_available, 2),
                "restricted_limit": round(restricted_limit, 2),
                "utilisation_pct": total_util,
            },
        }

    def _build_cash_tab(self, f, shared):
        forecast = shared["cash_forecast"]
        alerts = forecast["alerts"]
        bank_rows = shared["bank_rows"]
        is_manager = self.env.user.has_group(
            "biz_smart_finance.group_bsf_manager")

        banks_payload = self._build_bank_cash(f, shared)
        # ยอดปัจจุบันต่อธนาคาร (ไม่รวมแถว residual bank_id=0) — คำนวณครั้งเดียว
        # ใน _build_bank_cash แล้วอ่านต่อ ไม่ยิง AML ซ้ำ
        balances = {
            row["bank_id"]: row["current_balance"]
            for row in banks_payload["rows"] if row["bank_id"]
        }

        total_cash = forecast["opening"]
        restricted_cash = 0.0
        for row in bank_rows:
            bid = row["id"]
            if row["is_restricted"]:
                restricted_cash += balances.get(bid, 0.0)
            else:
                restricted_cash += self._conv(
                    shared, row["restricted_amount"], row["company_id"])
        restricted_cash = round(restricted_cash, 2)
        available_cash = round(total_cash - restricted_cash, 2)

        closing = forecast["closing"]
        if closing:
            min_index = min(range(len(closing)), key=lambda i: closing[i])
            min_13w = closing[min_index]
            min_13w_label = forecast["weeks"][min_index]["label"]
        else:
            min_13w, min_13w_label = 0.0, ""

        if balances:
            top_bank_id = max(balances, key=lambda b: balances[b])
            concentration_pct = (
                round(balances[top_bank_id] / total_cash * 100.0, 1)
                if total_cash else 0.0)
            top_bank_label = next(
                (row["name"] for row in bank_rows if row["id"] == top_bank_id),
                "")
        else:
            concentration_pct = 0.0
            top_bank_label = ""

        bank_name_map = {row["id"]: row["name"] for row in bank_rows}
        transfers_all = self.env["biz.smart.finance.bank.transfer"].search(
            [("company_id", "in", f["cids"])],
            order="execution_date desc, id desc", limit=200)
        transfer_rows = [{
            "id": tr.id,
            "source_bank_id": tr.source_bank_id.id,
            "source_bank_name": bank_name_map.get(
                tr.source_bank_id.id, tr.source_bank_id.name),
            "dest_bank_id": tr.dest_bank_id.id,
            "dest_bank_name": bank_name_map.get(
                tr.dest_bank_id.id, tr.dest_bank_id.name),
            "amount": round(self._conv(shared, tr.amount, tr.company_id.id), 2),
            "execution_date": str(tr.execution_date),
            "purpose": tr.purpose,
            "state": tr.state,
            "origin": tr.origin,
        } for tr in transfers_all]
        transfer_total = round(sum(
            r["amount"] for r in transfer_rows if r["state"] != "cancel"), 2)

        return {
            "forecast": forecast,
            "min_cash_alert": {
                "count": len(alerts),
                "first_label": alerts[0]["label"] if alerts else "",
                "last_label": alerts[-1]["label"] if alerts else "",
                "worst_gap": max((a["gap"] for a in alerts), default=0.0),
                "min_cash": forecast["min_cash"],
                "has_min_cash": forecast["has_min_cash"],
            },
            "collection_review": forecast.get("collection_review", []),
            "operating_buffer": round(
                forecast["min_cash"]
                * (1.0 + self._bank_operating_buffer_pct(shared) / 100.0), 2),
            "kpis": {
                "total_cash": round(total_cash, 2),
                "available_cash": available_cash,
                "restricted_cash": restricted_cash,
                "min_13w": round(min_13w, 2),
                "min_13w_label": min_13w_label,
                "concentration_pct": concentration_pct,
                "top_bank_label": top_bank_label,
            },
            "banks": banks_payload,
            "facilities": self._build_facilities(f, shared),
            "transfers": {
                "rows": transfer_rows,
                "total": transfer_total,
                "can_edit": is_manager,
            },
        }

    @api.model
    def action_bsf_suggest_transfers(self, filters=None):
        """เสนอแผนโอนระหว่างธนาคาร (manager เท่านั้น) จากธนาคารที่คาดว่าจะ
        หลุด buffer ใน 13 สัปดาห์ → จับคู่กับธนาคารที่มีเงินเหลือมากสุดใน
        สัปดาห์เดียวกัน (บริษัทเดียวกันเท่านั้น ตาม _check_banks)

        Idempotent: ลบ origin=suggested + state=draft ของบริษัทในขอบเขตทิ้ง
        ก่อนเสมอ แล้วค่อยสร้างใหม่ — ไม่แตะรายการที่ approved/done/กรอกมือ"""
        self._check_access()
        if self.env.su:
            is_manager = True
        else:
            is_manager = self.env.user.has_group(
                "biz_smart_finance.group_bsf_manager")
        if not is_manager:
            raise AccessError(_("ต้องเป็นสมาชิกกลุ่ม CFO Cockpit / Manager"))
        f = self._normalize_filters(filters or {})
        self = self.sudo()

        cids = f["cids"]
        Transfer = self.env["biz.smart.finance.bank.transfer"]
        Transfer.search([
            ("company_id", "in", cids),
            ("origin", "=", "suggested"),
            ("state", "=", "draft"),
        ]).unlink()

        shared = self._build_shared(f)
        shared["cash_forecast"] = self._build_cash_forecast(f, shared)
        banks_payload = self._build_bank_cash(f, shared)
        weeks_full = shared["weeks"]
        created = 0
        for alert in banks_payload["alerts"]:
            week = weeks_full[alert["week_index"]]
            company_id = next(
                (row["company_id"] for row in shared["bank_rows"]
                 if row["id"] == alert["bank_id"]), None)
            if not company_id:
                continue
            candidates = sorted(
                (
                    row for row in banks_payload["rows"]
                    if row["bank_id"] and row["bank_id"] != alert["bank_id"]
                    and next(
                        (b["company_id"] for b in shared["bank_rows"]
                         if b["id"] == row["bank_id"]), None) == company_id
                ),
                key=lambda row: row["weeks"][alert["week_index"]]["ending"],
                reverse=True,
            )
            if not candidates:
                continue
            source = candidates[0]
            source_week = source["weeks"][alert["week_index"]]
            headroom = source_week["ending"] - (source["min_balance"] or 0.0)
            amount = min(alert["gap"], headroom)
            if amount <= 0:
                continue
            Transfer.create({
                "source_bank_id": source["bank_id"],
                "dest_bank_id": alert["bank_id"],
                "amount": round(amount, 2),
                "execution_date": week["_from"],
                "purpose": "liquidity",
                "state": "draft",
                "origin": "suggested",
            })
            created += 1
        return {"created": created}

    # ------------------------------------------------------------------
    # Sales to Cash
    # ------------------------------------------------------------------
    def _utc_bounds(self, date_from, date_to):
        tz = pytz.timezone(self.env.user.tz or "Asia/Bangkok")
        start = tz.localize(datetime.combine(date_from, time.min))
        end = tz.localize(datetime.combine(date_to, time.max))
        to_naive_utc = lambda d: d.astimezone(pytz.utc).replace(tzinfo=None)
        return (
            fields.Datetime.to_string(to_naive_utc(start)),
            fields.Datetime.to_string(to_naive_utc(end)),
        )

    def _build_sales(self, f, shared):
        cids = f["cids"]
        dt_from, dt_to = self._utc_bounds(f["fy_start"], f["as_of"])

        booking_rows = self.env["sale.order"]._read_group(
            [
                ("state", "=", "sale"),
                ("company_id", "in", cids),
                ("date_order", ">=", dt_from),
                ("date_order", "<=", dt_to),
            ],
            groupby=["team_id", "company_id"],
            aggregates=["amount_untaxed:sum"],
        )
        booking_by_team = defaultdict(float)
        booking_by_company = defaultdict(float)
        booking_total = 0.0
        team_names = {}
        for team, company, amount in booking_rows:
            amount = self._conv(shared, amount, company.id)
            booking_total += amount
            booking_by_team[team.id if team else 0] += amount
            team_names[team.id if team else 0] = team.name if team else _("ไม่ระบุทีม")
            booking_by_company[company.id] += amount

        backlog_total = sum(shared.get("backlog_by_company", {}).values())

        # ใบแจ้งหนี้ + เก็บเงิน YTD (search_read เดียว ใช้ทั้งสองมิติ)
        # เฉพาะบริษัทที่ออกใบแจ้งหนี้ใน Odoo — ที่เหลืออ่านจาก External Invoices
        odoo_inv_cids = shared.get("inv_odoo_cids", cids)
        invoices = self.env["account.move"].search_read(
            [
                ("move_type", "in", ("out_invoice", "out_refund")),
                ("state", "=", "posted"),
                ("company_id", "in", odoo_inv_cids),
                ("invoice_date", ">=", str(f["fy_start"])),
                ("invoice_date", "<=", str(f["as_of"])),
            ],
            ["team_id", "company_id", "amount_untaxed_signed",
             "amount_total_signed", "amount_residual_signed"],
        ) if odoo_inv_cids else []
        # ระบบภายนอกไม่มีมิติทีมขาย — ทุกใบตกถังทีม 0 ("ไม่ระบุทีม")
        for row in self.env["biz.smart.finance.ext.invoice"].search_read(
            [
                ("company_id", "in", shared.get("inv_ext_cids", [])),
                ("doc_type", "=", "ar"),
                ("date", ">=", str(f["fy_start"])),
                ("date", "<=", str(f["as_of"])),
            ],
            ["company_id", "amount_total", "amount_untaxed",
             "amount_residual"],
        ) if shared.get("inv_ext_cids") else []:
            invoices.append({
                "team_id": False,
                "company_id": row["company_id"],
                "amount_untaxed_signed": (
                    row["amount_untaxed"] or row["amount_total"] or 0.0),
                "amount_total_signed": row["amount_total"] or 0.0,
                "amount_residual_signed": row["amount_residual"] or 0.0,
            })
        inv_by_team = defaultdict(float)
        col_by_team = defaultdict(float)
        inv_by_company = defaultdict(float)
        col_by_company = defaultdict(float)
        invoice_total = collection_total = 0.0
        for inv in invoices:
            rate = shared["fx"].get(inv["company_id"][0], 1.0)
            untaxed = (inv["amount_untaxed_signed"] or 0.0) * rate
            total = inv["amount_total_signed"] or 0.0
            residual = inv["amount_residual_signed"] or 0.0
            paid_ratio = 1.0 - (residual / total) if total else 0.0
            collected = untaxed * paid_ratio
            team_key = inv["team_id"][0] if inv["team_id"] else 0
            if inv["team_id"]:
                team_names.setdefault(team_key, inv["team_id"][1])
            invoice_total += untaxed
            collection_total += collected
            inv_by_team[team_key] += untaxed
            col_by_team[team_key] += collected
            inv_by_company[inv["company_id"][0]] += untaxed
            col_by_company[inv["company_id"][0]] += collected

        # Production / Install = earned value ของงาน BOQ (net_amount × %คืบ)
        # % ต้องคิดด้วยกติกาเดียวกับใบตั้งเบิก/ใบรับรอง คือ
        # ``ai.pm.earned.mixin._ev_raw_percent()`` — clamp 0..100 เสมอ และถ้า
        # โครงการตั้ง progress_basis='verified' ต้องใช้ min(plan, completion)
        # (เบิกได้ไม่เกินหลักฐานที่ตรวจรับแล้ว) ถ้าคิด plan_progress ดิบที่นี่
        # จอนี้จะไม่ตรงกับเอกสารเงินของโครงการที่ตั้ง verified ไว้
        tasks = self.env["project.task"].search_read(
            [
                ("boq_task_kind", "in", PRODUCTION_KINDS + INSTALL_KINDS),
                ("boq_line_id", "!=", False),
                ("project_id.company_id", "in", cids),
            ],
            ["boq_task_kind", "plan_progress", "boq_line_id", "project_id"],
        )
        boq_ids = {t["boq_line_id"][0] for t in tasks}
        boq_amounts = {}
        if boq_ids:
            for row in self.env["ai.pm.boq.line"].search_read(
                [("id", "in", list(boq_ids))], ["net_amount"],
            ):
                boq_amounts[row["id"]] = row["net_amount"] or 0.0
        # ฐาน % ต่อโครงการ — อ่านครั้งเดียวแทนการแตะ record รายงาน
        Earned = self.env["ai.pm.earned.mixin"]
        task_project_ids = {
            t["project_id"][0] for t in tasks if t["project_id"]
        }
        verified_project_ids = set()
        if task_project_ids:
            verified_project_ids = set(self.env["project.project"].search([
                ("id", "in", list(task_project_ids)),
                ("progress_basis", "=", Earned.EV_BASIS_VERIFIED),
            ]).ids)
        # ``completion_progress`` เป็น compute ไม่ stored และ recursive ลงลูก —
        # อ่านเฉพาะงานของโครงการที่ตั้ง verified จริง ๆ เท่านั้น ไม่ใช่ทั้งบริษัท
        completion_by_task = {}
        if verified_project_ids:
            verified_tasks = self.env["project.task"].browse([
                t["id"] for t in tasks
                if t["project_id"] and t["project_id"][0] in verified_project_ids
            ])
            for task_record in verified_tasks:
                completion_by_task[task_record.id] = (
                    task_record.completion_progress or 0.0
                )
        production_value = install_value = 0.0
        project_company = shared["project_company"]
        for task in tasks:
            project = task["project_id"]
            project_id = project[0] if project else 0
            percent = task["plan_progress"] or 0.0
            if project_id in verified_project_ids:
                # เบิกได้ไม่เกินหลักฐานที่ตรวจรับแล้ว — min() ไม่ใช่ค่าเฉลี่ย
                percent = min(percent, completion_by_task.get(task["id"], 0.0))
            percent = min(max(percent, 0.0), 100.0)
            earned = self._conv(
                shared,
                boq_amounts.get(task["boq_line_id"][0], 0.0) * percent / 100.0,
                project_company.get(project_id),
            )
            if task["boq_task_kind"] in PRODUCTION_KINDS:
                production_value += earned
            else:
                install_value += earned

        values = {
            "booking": booking_total,
            "backlog": backlog_total,
            "production": production_value,
            "install": install_value,
            "invoice": invoice_total,
            "collection": collection_total,
        }
        funnel = []
        prev = None
        for code, label in FUNNEL_STAGES:
            value = round(values[code], 2)
            conv = round(value / prev * 100.0, 1) if prev else None
            funnel.append({
                "stage": code, "label": label,
                "value": value, "conv_pct": conv,
            })
            prev = values[code] or None

        def conversion_table(booking_map, col_map, name_of):
            rows = []
            for key in sorted(
                set(booking_map) | set(col_map),
                key=lambda k: -(booking_map.get(k, 0.0)),
            ):
                booking = booking_map.get(key, 0.0)
                collected = col_map.get(key, 0.0)
                rows.append({
                    "key": key,
                    "name": name_of(key),
                    "booking": round(booking, 2),
                    "collection": round(collected, 2),
                    "conv_pct": round(collected / booking * 100.0, 1) if booking else 0.0,
                })
            return rows

        companies = {c.id: c.name for c in self.env["res.company"].browse(f["cids"])}
        by_channel = conversion_table(
            booking_by_team, col_by_team,
            lambda k: team_names.get(k, _("ไม่ระบุทีม")))
        by_bu = conversion_table(
            booking_by_company, col_by_company,
            lambda k: companies.get(k, "?"))

        # ---- metrics ----
        revenue_t12m = shared["pl_t12m"]["total"]["revenue"]
        ar_balance = self._sum_type(shared, "bal_cum", (AR_TYPE,))
        ar_prior = self._sum_type(shared, "bal_cum_prior", (AR_TYPE,))
        # รายได้ 12 เดือนก่อนหน้าปีก่อน ใช้ prior-YTD scale เต็มปีไม่ได้ —
        # ประมาณจาก prior YTD (ช่วงเวลาเท่ากันกับ YTD ปีนี้) เพื่อเทียบ DSO YoY
        revenue_prior_span = shared["pl_prior"]["total"]["revenue"]
        revenue_ytd = shared["pl_ytd"]["total"]["revenue"]
        dso = round(ar_balance / revenue_t12m * 365.0) if revenue_t12m else None
        dso_prior = (
            round(ar_prior / revenue_prior_span * (f["as_of"] - f["fy_start"]).days)
            if revenue_prior_span else None
        )
        today = f["today"]
        overdue60 = sum(
            item["amount_residual"] for item in shared["ar_items"]
            if (item["date_maturity"] or item["date"])
            and (today - (item["date_maturity"] or item["date"])).days > 60
        )
        dso_targets = [
            cfg.dso_target_days for cfg in shared["cfg_map"].values()
            if cfg.dso_target_days
        ]
        return {
            "funnel": funnel,
            "by_channel": by_channel,
            "by_bu": by_bu,
            "metrics": {
                "dso_days": dso,
                "dso_prior_days": dso_prior,
                "dso_delta": (dso - dso_prior)
                if dso is not None and dso_prior is not None else None,
                "dso_target": max(dso_targets) if dso_targets else None,
                "backlog_coverage_x": round(backlog_total / revenue_t12m, 2)
                if revenue_t12m else None,
                "billing_to_collection_pct": round(
                    collection_total / invoice_total * 100.0, 1
                ) if invoice_total else 0.0,
                "total_ar": round(
                    sum(i["amount_residual"] for i in shared["ar_items"]), 2),
                "overdue_60": round(overdue60, 2),
                "revenue_ytd": round(revenue_ytd, 2),
            },
        }

    # ------------------------------------------------------------------
    # Project Margin
    # ------------------------------------------------------------------
    def _build_margin(self, f, shared):
        projects = self.env["project.project"].search([
            ("company_id", "in", f["cids"]), ("active", "=", True),
        ])
        # eac เป็น compute stored → read_group ได้; margin ของโปรเจกต์
        # (gate1/gate5) ไม่ stored → อ่านเป็น batch แล้วกรองใน Python
        wp_rows = self.env["ai.pm.work.package"]._read_group(
            [("project_id", "in", projects.ids)],
            groupby=["project_id"],
            aggregates=["eac:sum", "cost_to_date:sum"],
        )
        eac_by_project = {p.id: (eac or 0.0, ctd or 0.0) for p, eac, ctd in wp_rows}
        # แท็บ Forecast ต้องใช้ต้นทุนคงเหลือชุด**เดียวกัน**กับแท็บนี้ ไม่งั้นสองจอ
        # จะบอกตัวเลขคนละตัว — จึงส่งต่อผ่าน shared แทนการคำนวณซ้ำ
        shared["projects"] = projects
        shared["eac_by_project"] = eac_by_project

        # โปรเจกต์ที่ไม่มีมูลค่าสัญญาถูก `continue` ทิ้งอยู่แล้วด้านล่าง แต่การ
        # จะรู้ต้องแตะ `contract_revenue` ซึ่งเป็น compute **ที่ไม่ stored** และ
        # ลากทั้ง BOQ/PO/MO/Vendor bill ของโปรเจกต์นั้นขึ้นมา — คัดด้วย
        # aggregate จาก *แหล่งเดียวกัน* (Σ net_amount ของบรรทัด BOQ ซึ่ง
        # `_compute_close_costs` ใช้เป็นนิยามของ contract_revenue) ก่อน แล้ว
        # ค่อยแตะ compute เฉพาะโปรเจกต์ที่รอด  ห้ามใช้ยอดนี้เป็นตัวเลขบนจอ —
        # ใช้เป็น "ตัวคัด" เท่านั้น ตัวเลขยังอ่านจากฟิลด์เหมือนเดิมทุกตัว
        revenue_rows = self.env["ai.pm.boq.line"]._read_group(
            [("project_id", "in", projects.ids), ("plan_type", "=", "boq")],
            groupby=["project_id"], aggregates=["net_amount:sum"],
        )
        with_revenue = {
            project.id for project, total in revenue_rows if (total or 0.0) > 0
        }
        # `shared["projects"]` ต้องเป็นชุดเต็มต่อไป — `_build_forecast` ใช้หา
        # งบ BOQ ที่ยังไม่ผูกพัน ซึ่งมีได้แม้โปรเจกต์ยังไม่มีมูลค่าสัญญา
        margin_projects = projects.browse(
            [pid for pid in projects.ids if pid in with_revenue])

        margin_hit = shared["scenario_fx"]["margin_hit_pct"]
        bubbles, risk_rows = [], []
        budget_margin_total = forecast_margin_total = revenue_total = 0.0
        for project in margin_projects:
            # เปอร์เซ็นต์ margin ไม่ต้องแปลงสกุล — แปลงเฉพาะยอดเงิน
            money = lambda v: self._conv(shared, v, project.company_id.id)
            revenue = money(project.contract_revenue or 0.0)
            if revenue <= 0:
                continue
            budget_pct = project.expected_margin_percent or 0.0
            if not project.budget_total:
                budget_pct = project.profit_percent or 0.0
            forecast_pct = (project.profit_percent or 0.0) - margin_hit
            eac, cost_to_date = eac_by_project.get(project.id, (0.0, 0.0))
            cost_basis = money(
                project.actual_cost or project.accounting_actual_cost
                or project.committed_cost_total or 0.0
            )
            budget_total = money(project.budget_total or 0.0)
            ctc = max((money(eac) or budget_total) - cost_basis, 0.0)
            row = {
                "project_id": project.id,
                "name": project.name,
                "company": project.company_id.name or "",
                "budget_margin_pct": round(budget_pct, 1),
                "forecast_margin_pct": round(forecast_pct, 1),
                "risk_pp": round(budget_pct - forecast_pct, 1),
                "budget_total": round(budget_total, 2),
                "contract_revenue": round(revenue, 2),
                "cost_to_complete": round(ctc, 2),
            }
            bubbles.append(row)
            risk_rows.append(row)
            revenue_total += revenue
            budget_margin_total += revenue * budget_pct / 100.0
            forecast_margin_total += revenue * forecast_pct / 100.0

        shared["margin_rows"] = bubbles
        risk_rows = sorted(risk_rows, key=lambda r: -r["risk_pp"])[:10]
        leakage = budget_margin_total - forecast_margin_total
        leakage_pct = (
            round(leakage / budget_margin_total * 100.0, 1)
            if budget_margin_total else 0.0
        )
        thresholds = [
            cfg.margin_leakage_alert_pct
            for cfg in shared["cfg_map"].values()
            if cfg.margin_leakage_alert_pct
        ]
        threshold = min(thresholds) if thresholds else None
        shared["margin_leakage_pct"] = leakage_pct
        shared["margin_leakage_threshold"] = threshold
        # แท็บ Risk ใช้ "ยอดเงิน" ที่หลุด ไม่ใช่เปอร์เซ็นต์ (ตาราง Early-Warning
        # แสดงผลกระทบเป็นเงิน) — คำนวณที่นี่ที่เดียวแล้วส่งต่อ
        shared["margin_leakage_amount"] = leakage
        shared["margin_revenue_total"] = revenue_total

        vo_records = self.env["biz.smart.finance.vo"].search([
            ("company_id", "in", f["cids"]),
        ])
        vo_table = [{
            "id": vo.id,
            "project_id": vo.project_id.id,
            "project": vo.project_id.name,
            "name": vo.name,
            "amount": round(vo.amount, 2),
            "margin_impact": round(vo.margin_impact, 2),
            "state": vo.state,
            "date": str(vo.date) if vo.date else "",
        } for vo in vo_records]

        return {
            "bubbles": bubbles,
            "leakage": {
                "budget_margin": round(budget_margin_total, 2),
                "forecast_margin": round(forecast_margin_total, 2),
                "leakage_amount": round(leakage, 2),
                "leakage_pct": leakage_pct,
                "threshold": threshold,
                "alert": bool(threshold is not None and leakage_pct > threshold),
            },
            "risk_table": risk_rows,
            "vo_table": vo_table,
            "scenario_hit_pp": margin_hit,
        }

    # ------------------------------------------------------------------
    # AP & Payment Plan
    # ------------------------------------------------------------------
    def _build_ap(self, f, shared):
        today = f["today"]
        weeks = shared["weeks"][:AP_CAL_WEEKS]

        # ปฏิทินจ่าย 6 สัปดาห์: approved = บิลตั้งแล้ว / pending = แผนที่ยังไม่ตั้งบิล
        calendar_rows = [
            {"index": w["index"], "label": w["label"], "sub": w["sub"],
             "approved": 0.0, "pending": 0.0}
            for w in weeks
        ]
        overdue_total = 0.0
        for item in shared["ap_items"]:
            due = item["date_maturity"] or item["date"]
            if due and due < today:
                overdue_total += item["amount_residual"]
                continue
            index = self._week_index(shared["weeks"], due)
            if index is not None and index < AP_CAL_WEEKS:
                calendar_rows[index]["approved"] += item["amount_residual"]

        vendor_lines = self.env["ai.pm.vendor.payment.line"].search_read(
            [("project_id.company_id", "in", f["cids"])],
            ["residual_amount", "due_date", "expected_pay_date", "bill_ids",
             "partner_id", "project_id"],
        )
        project_company = shared["project_company"]
        for line in vendor_lines:
            if line["bill_ids"] or (line["residual_amount"] or 0.0) <= 0:
                continue
            # ใช้ expected_pay_date เป็นหลักให้ตรงกับ _forecast_sources และกับ
            # วันที่แอปผู้รับเหมาบอกไว้ — due_date ดิบเป็นแค่กำหนดตามแผน ทำให้งวด
            # เดียวกันตกคนละสัปดาห์ระหว่างแท็บ AP กับ Cash Forecast บนจอเดียวกัน
            index = self._week_index(
                shared["weeks"], line["expected_pay_date"] or line["due_date"])
            if index is not None and index < AP_CAL_WEEKS:
                project = line["project_id"]
                calendar_rows[index]["pending"] += self._conv(
                    shared, line["residual_amount"],
                    project_company.get(project[0] if project else 0))
        for row in calendar_rows:
            row["approved"] = round(row["approved"], 2)
            row["pending"] = round(row["pending"], 2)

        # aging 4 ถัง
        aging = {"current": 0.0, "b1_30": 0.0, "b31_60": 0.0, "b60_plus": 0.0}
        supplier_balance = defaultdict(float)
        supplier_overdue = defaultdict(float)
        supplier_max_days = defaultdict(int)
        supplier_names = {}
        for item in shared["ap_items"]:
            due = item["date_maturity"] or item["date"]
            days = (today - due).days if due else 0
            amount = item["amount_residual"]
            if days <= 0:
                aging["current"] += amount
            elif days <= 30:
                aging["b1_30"] += amount
            elif days <= 60:
                aging["b31_60"] += amount
            else:
                aging["b60_plus"] += amount
            partner = item["partner_id"]
            key = partner[0] if partner else 0
            supplier_names[key] = partner[1] if partner else _("ไม่ระบุ")
            supplier_balance[key] += amount
            if days > 0:
                supplier_overdue[key] += amount
                supplier_max_days[key] = max(supplier_max_days[key], days)
        aging_total = sum(aging.values())
        aging = {k: round(v, 2) for k, v in aging.items()}

        strategic_ids = set()
        partner_ids = [k for k in supplier_balance if k > 0]
        if partner_ids:
            strategic_ids = set(self.env["res.partner"].search([
                ("id", "in", partner_ids),
                ("bsf_strategic_supplier", "=", True),
            ]).ids)

        top_suppliers = []
        max_balance = max(supplier_balance.values(), default=0.0)
        for key, balance in sorted(
            supplier_balance.items(), key=lambda kv: -kv[1]
        )[:10]:
            top_suppliers.append({
                "partner_id": self._drill_partner(key),
                "name": supplier_names[key],
                "balance": round(balance, 2),
                "pct_of_total": round(balance / aging_total * 100.0, 1)
                if aging_total else 0.0,
                "overdue": round(supplier_overdue.get(key, 0.0), 2),
                "strategic": key in strategic_ids,
            })

        priority = []
        for key, balance in supplier_balance.items():
            if balance <= 0:
                continue
            score = (
                0.5 * min(supplier_max_days.get(key, 0), 90) / 90.0
                + 0.3 * (balance / max_balance if max_balance else 0.0)
                + 0.2 * (1.0 if key in strategic_ids else 0.0)
            )
            priority.append({
                "partner_id": self._drill_partner(key),
                "name": supplier_names[key],
                "score": int(round(score * 100)),
                "amount": round(balance, 2),
                "overdue_days": supplier_max_days.get(key, 0),
                "strategic": key in strategic_ids,
            })
        priority = sorted(priority, key=lambda p: -p["score"])[:10]

        # PO วัสดุคงค้าง (เตรียมไว้แล้วใน _build_cash_forecast)
        committed = {"b30": 0.0, "b31_60": 0.0, "b61_90": 0.0, "b90_plus": 0.0}
        po_count = set()
        for line in shared.get("po_open_lines", []):
            day = line["date_planned"]
            days = (day - today).days if day else 0
            if days <= 30:
                committed["b30"] += line["amount"]
            elif days <= 60:
                committed["b31_60"] += line["amount"]
            elif days <= 90:
                committed["b61_90"] += line["amount"]
            else:
                committed["b90_plus"] += line["amount"]
            po_count.add(line["order_id"][0] if line["order_id"] else 0)
        committed = {k: round(v, 2) for k, v in committed.items()}
        committed["total"] = round(sum(committed.values()), 2)
        committed["count"] = len(po_count)

        forecast = shared["cash_forecast"]
        conflict_weeks = [
            {"label": a["label"], "shortfall": a["gap"]}
            for a in forecast["alerts"]
        ]
        return {
            "calendar": calendar_rows,
            "source": self._invoice_source_group(f, shared),
            "overdue_total": round(overdue_total, 2),
            "aging": dict(aging, total=round(aging_total, 2)),
            "top_suppliers": top_suppliers,
            "priority": priority,
            "committed_po": committed,
            "conflict": {
                "weeks": conflict_weeks,
                "has_conflict": bool(conflict_weeks),
            },
        }

    # ------------------------------------------------------------------
    # Controlling (สไตล์ SAP CO) — ศูนย์ต้นทุน × งบประมาณ × ภาระผูกพัน
    # ------------------------------------------------------------------
    def _controlling_plans(self):
        """แผนวิเคราะห์ระดับราก = มิติที่เลือกดูได้ (SAP: cost/profit center)"""
        return self.env["account.analytic.plan"].sudo().search(
            [("parent_id", "=", False)], order="sequence, id")

    def _controlling_column(self, plan):
        """คอลัมน์จริงบน account.analytic.line ของแผนนี้

        ห้าม hardcode `x_planN_id` — Odoo สร้างคอลัมน์ให้ตอนสร้างแผน และ
        แผนลูกใช้คอลัมน์ของราก ต้องถาม `_column_name()` เสมอ แล้วกันพลาด
        ด้วยการเช็ค registry (อาจยังไม่ reload หลังเพิ่งสร้างแผน)
        """
        if not plan:
            return False
        column = plan._column_name()
        if column not in self.env["account.analytic.line"]._fields:
            return False
        return column

    def _build_controlling(self, f, shared):
        plans = self._controlling_plans()
        plan = plans.browse(f["plan_id"]) if f["plan_id"] else plans[:1]
        column = self._controlling_column(plan)
        # งบมาได้สองแหล่งต่อบริษัท: om_account_budget ของ Odoo หรือตาราง
        # External Budgets (สำหรับบริษัทที่ตั้งงบไว้ในระบบอื่น)
        ext_budget_cids = [
            cid for cid in f["cids"]
            if self._budget_source(shared, cid) == "external"
        ]
        odoo_budget_cids = [
            cid for cid in f["cids"] if cid not in ext_budget_cids
        ]
        budget_sources = {
            cid: self._budget_source(shared, cid) for cid in f["cids"]
        }
        base = {
            "plans": [{"id": p.id, "name": p.name} for p in plans],
            "plan_id": plan.id if plan else False,
            "plan_name": plan.name if plan else "",
            "column": column or "",
            # om_account_budget ไม่ใช่ dependency — จอต้องอยู่ได้ถ้าไม่มี
            "budget_available": bool(ext_budget_cids) or (
                bool(odoo_budget_cids)
                and "crossovered.budget.lines" in self.env),
            "budget_source": self._mixed_source(budget_sources)
            if budget_sources else "odoo",
        }
        if not column:
            return dict(base, configured=False, rows=[], totals={},
                        by_account_type=[], has_gl_link=False)

        cids = f["cids"]
        date_from, date_to = f["fy_start"], f["as_of"]
        accounts = self.env["account.analytic.account"].sudo().search([
            ("plan_id", "child_of", plan.id),
        ])
        acc_name = {a.id: a.name for a in accounts}
        acc_code = {a.id: a.code or "" for a in accounts}
        allowed_ids = set(accounts.ids)

        # ---- Actual: analytic line (amount ติดลบ = ต้นทุน) ----
        actual_cost = defaultdict(float)
        actual_revenue = defaultdict(float)

        def read_side(operator, bucket, sign):
            rows = self.env["account.analytic.line"].sudo()._read_group(
                [
                    (column, "in", list(allowed_ids)),
                    ("company_id", "in", cids),
                    ("date", ">=", str(date_from)),
                    ("date", "<=", str(date_to)),
                    ("amount", operator, 0.0),
                ],
                groupby=[column, "company_id"],
                aggregates=["amount:sum"],
            )
            for account, company, amount in rows:
                bucket[account.id] += sign * self._conv(
                    shared, amount, company.id)

        read_side("<", actual_cost, -1.0)
        read_side(">", actual_revenue, 1.0)

        # ---- Budget: crossovered.budget.lines เฉลี่ยตามจำนวนวันที่ทับช่วง ----
        # om_account_budget ให้ผู้ใช้กรอกงบต้นทุนเป็นบวกหรือลบก็ได้ จึงใช้ abs()
        # เหมือน biz_dashboard_finance (อย่าให้สองจอตีความงบก้อนเดียวกันคนละแบบ)
        budget = defaultdict(float)

        def add_budget(amount, line_from, line_to, company_id):
            """เฉลี่ยงบของช่วง [line_from, line_to] ตามวันที่ทับกับงวดที่ดูอยู่"""
            span = (line_to - line_from).days + 1
            if span <= 0:
                return 0.0
            overlap = (min(line_to, date_to) - max(line_from, date_from)).days + 1
            if overlap <= 0:
                return 0.0
            return self._conv(
                shared, abs(amount or 0.0) * overlap / span, company_id)

        if odoo_budget_cids and "crossovered.budget.lines" in self.env:
            budget_lines = self.env["crossovered.budget.lines"].sudo(
            ).search_read(
                [
                    ("analytic_account_id", "in", list(allowed_ids)),
                    ("company_id", "in", odoo_budget_cids),
                    ("crossovered_budget_state", "in",
                     ("confirm", "validate", "done")),
                    ("date_from", "<=", str(date_to)),
                    ("date_to", ">=", str(date_from)),
                ],
                ["analytic_account_id", "planned_amount",
                 "date_from", "date_to", "company_id"],
            )
            for line in budget_lines:
                budget[line["analytic_account_id"][0]] += add_budget(
                    line["planned_amount"], line["date_from"], line["date_to"],
                    line["company_id"][0] if line["company_id"] else False)

        if ext_budget_cids:
            for line in self.env["biz.smart.finance.ext.budget"].search_read(
                [
                    ("analytic_account_id", "in", list(allowed_ids)),
                    ("company_id", "in", ext_budget_cids),
                    ("date_from", "<=", str(date_to)),
                    ("date_to", ">=", str(date_from)),
                ],
                ["analytic_account_id", "amount", "date_from", "date_to",
                 "company_id"],
            ):
                budget[line["analytic_account_id"][0]] += add_budget(
                    line["amount"], line["date_from"], line["date_to"],
                    line["company_id"][0] if line["company_id"] else False)

        # ---- Commitment: PO ยืนยันแล้วส่วนที่ยังไม่ตั้งบิล ----
        # analytic_distribution เป็น jsonb {"12": 100.0} หรือ {"12,34": 100.0}
        # คีย์ที่มีคอมมาคือ "หนึ่งบรรทัดกระจายข้ามหลายแผนพร้อมกัน" — แต่ละ id
        # ได้ % เต็มของแผนตัวเอง จึง**ไม่หาร**ตามจำนวน id
        commitment = defaultdict(float)
        po_lines = self.env["purchase.order.line"].sudo().search_read(
            [
                ("state", "in", ("purchase", "done")),
                ("company_id", "in", cids),
                ("display_type", "=", False),
                ("analytic_distribution", "!=", False),
            ],
            ["product_qty", "qty_invoiced", "price_subtotal",
             "analytic_distribution", "company_id"],
        )
        for line in po_lines:
            qty = line["product_qty"] or 0.0
            if not qty:
                continue
            open_ratio = max(qty - (line["qty_invoiced"] or 0.0), 0.0) / qty
            open_amount = (line["price_subtotal"] or 0.0) * open_ratio
            if open_amount <= 0:
                continue
            open_amount = self._conv(
                shared, open_amount,
                line["company_id"][0] if line["company_id"] else False)
            for key, percent in (line["analytic_distribution"] or {}).items():
                for raw_id in str(key).split(","):
                    try:
                        account_id = int(raw_id)
                    except ValueError:
                        continue
                    if account_id in allowed_ids:
                        commitment[account_id] += (
                            open_amount * (percent or 0.0) / 100.0)

        # ---- ประกอบตาราง ----
        rows = []
        for account_id in set(actual_cost) | set(actual_revenue) \
                | set(budget) | set(commitment):
            cost = actual_cost.get(account_id, 0.0)
            revenue = actual_revenue.get(account_id, 0.0)
            plan_amount = budget.get(account_id, 0.0)
            committed = commitment.get(account_id, 0.0)
            consumed = cost + committed
            rows.append({
                "analytic_id": account_id,
                "name": acc_name.get(account_id, "?"),
                "code": acc_code.get(account_id, ""),
                "actual_cost": round(cost, 2),
                "actual_revenue": round(revenue, 2),
                "actual_net": round(revenue - cost, 2),
                "budget": round(plan_amount, 2),
                "commitment": round(committed, 2),
                "available": round(plan_amount - consumed, 2),
                "utilization_pct": round(consumed / plan_amount * 100.0, 1)
                if plan_amount else None,
                "over_budget": bool(plan_amount and consumed > plan_amount),
            })
        rows.sort(key=lambda r: -(r["budget"] or r["actual_cost"]))

        totals = {
            key: round(sum(r[key] for r in rows), 2)
            for key in ("actual_cost", "actual_revenue", "actual_net",
                        "budget", "commitment", "available")
        }
        totals["utilization_pct"] = round(
            (totals["actual_cost"] + totals["commitment"])
            / totals["budget"] * 100.0, 1) if totals["budget"] else None
        totals["over_count"] = sum(1 for r in rows if r["over_budget"])

        # ---- แยกตามประเภทบัญชี GL (เฉพาะ analytic line ที่ผูก move line) ----
        by_type_rows = self.env["account.analytic.line"].sudo()._read_group(
            [
                (column, "in", list(allowed_ids)),
                ("company_id", "in", cids),
                ("date", ">=", str(date_from)),
                ("date", "<=", str(date_to)),
                ("general_account_id", "!=", False),
            ],
            groupby=["general_account_id", "company_id"],
            aggregates=["amount:sum"],
        )
        by_type = defaultdict(float)
        for account, company, amount in by_type_rows:
            # ต้นทุน = amount ติดลบ → กลับเครื่องหมายให้อ่านเป็นบวก
            by_type[account.account_type] -= self._conv(
                shared, amount, company.id)
        by_account_type = sorted(
            ({"account_type": key, "amount": round(value, 2)}
             for key, value in by_type.items() if round(value, 2)),
            key=lambda r: -abs(r["amount"]),
        )

        return dict(
            base,
            configured=True,
            rows=rows[:25],
            row_count=len(rows),
            totals=totals,
            by_account_type=by_account_type,
            # analytic line ในระบบนี้ส่วนใหญ่มาจาก timesheet ซึ่งไม่มี GL
            # ผูกอยู่ — บอก client ให้ซ่อนการ์ดแทนที่จะโชว์การ์ดว่าง
            has_gl_link=bool(by_account_type),
            date_from=str(date_from),
            date_to=str(date_to),
        )

    # ------------------------------------------------------------------
    # Compare (BI) — หลายงวดเรียงเป็นคอลัมน์ (ปี / ไตรมาส / เดือน)
    # ------------------------------------------------------------------
    def _cmp_balances(self, f, shared, date_from, date_to, rates):
        """{account_id: balance} ของหน้าต่างหนึ่ง แปลงด้วยอัตราของคอลัมน์นั้น

        ห้ามใช้ shared["fx"]/["fx_prior"] — แต่ละคอลัมน์ต้องใช้ closing rate
        ณ วันสิ้นคอลัมน์ของตัวเอง (กติกา one rate per column ดู _fx_rates)
        """
        acc_company = shared["acc_company"]
        domain = [
            ("parent_state", "=", "posted"),
            ("company_id", "in", f["cids"]),
            ("account_id", "in", list(acc_company)),
            ("date", "<=", str(date_to)),
        ]
        if date_from:
            domain.append(("date", ">=", str(date_from)))
        rows = self.env["account.move.line"]._read_group(
            domain, groupby=["account_id"], aggregates=["balance:sum"],
        )
        return {
            acc.id: (bal or 0.0) * rates.get(acc_company.get(acc.id), 1.0)
            for acc, bal in rows
        }

    @staticmethod
    def _bs_map_union(bs_map, keys):
        """union ของบัญชีที่ผูกไว้หลายคีย์ใน bs_map_ids (mapping งบดุล)"""
        out = set()
        for key in keys:
            out |= bs_map.get(key, set())
        return out

    def _waterfall_maps(self, shared):
        """ชุด mapping บัญชีของงบ waterfall ทั้งสามงบ

        ใช้ร่วมทุกที่ที่คิดเป็นคอลัมน์ (Compare BI, แท็บช่องทางขาย) เพื่อให้
        ผูกกับ mapping ชุดเดียวกับ `_build_statements` ไม่แตกเป็นสูตรที่สอง
        """
        by_type = defaultdict(list)
        for account_id, atype in shared["acc_type"].items():
            by_type[atype].append(account_id)
        map_ids = {
            "dep": set(shared["dep_ids"])
            | set(by_type.get("expense_depreciation", ())),
            "int": set(shared["int_ids"]),
            "tax": set(shared["tax_ids"]),
        }
        bs_map = shared["bs_map_ids"]
        cf_debt = self._bs_map_union(bs_map, CF_DEBT_KEYS)
        cf_lease = self._bs_map_union(bs_map, CF_LEASE_KEYS)
        return {
            "by_type": by_type,
            "map_ids": map_ids,
            "distributed": map_ids["dep"] | map_ids["int"] | map_ids["tax"],
            "bs_map": bs_map,
            "bs_all": set().union(*bs_map.values()) if bs_map else set(),
            "eq_mapped": (bs_map.get("paid_in_capital", set())
                          | bs_map.get("legal_reserve", set())),
            "cf_div": shared["cf_dividend_ids"],
            "cf_invest_other": self._bs_map_union(
                bs_map, CF_INVEST_OTHER_KEYS),
            "cf_carveout": cf_debt | cf_lease,
        }

    def _cf_drill(self, shared, maps, src):
        """(types, account_ids, exclude_ids) ของบรรทัดงบกระแสเงินสด — ใช้ร่วม
        ทั้งแท็บ Compare (BI) และแท็บช่องทางขาย (ดู openCmpCell ฝั่งจอ)"""
        def mu(keys):
            return self._bs_map_union(maps["bs_map"], keys)

        kind = src[0]
        if kind == "pl":
            return ((list(PL_TYPES), [], []) if src[1] == "net"
                    else ([], sorted(maps["map_ids"]["dep"]), []))
        if kind == "d_type":
            return list(src[1]), [], []
        if kind == "d_type_ex":
            return list(src[1]), [], sorted(mu(src[2]))
        if kind == "d_ids":
            return [], sorted(mu(src[1])), []
        if kind == "map":
            return [], sorted(maps["cf_div"]), []
        if kind == "capex":
            return ["asset_fixed"], [], []
        if kind == "invest_other":
            return ["asset_non_current"], sorted(maps["cf_invest_other"]), []
        if kind == "wc_other":
            return (list(CF_OTHER_CA_TYPES + CF_OTHER_CL_TYPES), [],
                    sorted(set(shared["inv_ids"]) | maps["cf_carveout"]))
        if kind == "equity_fin":
            return (list(EQUITY_TYPES + CF_FIN_LIAB_TYPES), [],
                    sorted(maps["cf_div"] | maps["cf_carveout"]))
        return [], [], []

    def _waterfall_columns(self, f, shared, cfg_map, windows, maps=None):
        """{key: [ค่าต่อคอลัมน์]} ของทุกบรรทัด PNL/BS/CF_WATERFALL

        เครื่องคิดคอลัมน์ตัวเดียวของทั้งแท็บ Compare (BI) และแท็บช่องทางขาย:
        คอลัมน์หนึ่ง = หน้าต่างวันที่หนึ่ง — P&L/กระแสเงินสดใช้ยอด **ไหล** ใน
        หน้าต่าง งบดุลใช้ยอด **สะสม** ณ วันสิ้นคอลัมน์ และ **หนึ่งอัตรา
        แลกเปลี่ยนต่อคอลัมน์** (closing rate ของวันสิ้นคอลัมน์นั้น)
        """
        maps = maps or self._waterfall_maps(shared)
        cmp_bs_map = maps["bs_map"]
        cmp_bs_all = maps["bs_all"]
        cmp_eq_mapped = maps["eq_mapped"]
        cmp_cf_div = maps["cf_div"]
        cmp_cf_invest_other = maps["cf_invest_other"]
        cmp_cf_carveout = maps["cf_carveout"]

        def _cmp_mu(keys):
            return self._bs_map_union(cmp_bs_map, keys)

        values = defaultdict(list)
        for col in windows:
            rates = self._fx_rates_memo(
                shared, f["cids"], col["_to"], f["presentation_currency"])
            flow = self._cmp_balances(
                f, shared, col["_from"], col["_to"], rates)
            cumulative = self._cmp_balances(f, shared, False, col["_to"], rates)

            # P&L ใช้เครื่องคิดเดียวกับ Overview/Statements — EBITDA จึงผูกกับ
            # mapping ค่าเสื่อม/ดอกเบี้ย/ภาษีชุดเดิม ไม่แตกเป็นสูตรที่สอง
            shared["_cmp_flow"] = flow
            try:
                pl = self._pl_from_balances(shared, cfg_map, "_cmp_flow")["total"]
            finally:
                shared.pop("_cmp_flow", None)
            for _kind, key, _label, _sign, _src in PNL_WATERFALL:
                values[key].append(pl[key])
            values["revenue"].append(pl["revenue"])

            def cum_ids(ids):
                return sum(cumulative.get(a, 0.0) for a in ids)

            def cum_types(types, exclude=()):
                return sum(
                    bal for account_id, bal in cumulative.items()
                    if shared["acc_type"].get(account_id) in types
                    and account_id not in exclude
                )

            # ---- งบดุลแบบ waterfall: ยอดสะสม ณ วันสิ้นคอลัมน์ ----
            bs_col = {}
            bs_sec_run = defaultdict(float)
            for bkind, bsec, bkey, _blabel, bsrc in BS_WATERFALL:
                if bkind == "subtotal":
                    if bsrc[0] == "lines":
                        v = bs_sec_run[bsrc[1]]
                    else:
                        v = sum(bs_col[k] for k in bsrc[1])
                    bs_col[bkey] = v
                    values[bkey].append(v)
                    continue
                bsign = BS_SEC_SIGN[bsec]
                if bsrc[0] == "map":
                    v = bsign * cum_ids(cmp_bs_map.get(bsrc[1], ()))
                elif bsrc[0] == "type":
                    v = bsign * cum_types(bsrc[1])
                elif bsrc[0] == "type_ex":
                    v = bsign * cum_types(bsrc[1], cmp_bs_all)
                else:  # equity_plug
                    v = (bsign * cum_types(
                        ("equity", "equity_unaffected"), cmp_eq_mapped)
                        - cum_types(PL_TYPES))
                bs_col[bkey] = v
                values[bkey].append(v)
                bs_sec_run[bsec] += v

            # ---- งบกระแสเงินสด waterfall: กระแสในหน้าต่างของคอลัมน์ (flow) ----
            def flow_type(types, exclude=()):
                return -sum(
                    bal for account_id, bal in flow.items()
                    if shared["acc_type"].get(account_id) in types
                    and account_id not in exclude)

            def flow_ids(ids):
                return -sum(flow.get(a, 0.0) for a in ids)

            def cf_col_val(src):
                kind = src[0]
                if kind == "pl":
                    return pl[src[1]]
                if kind == "d_type":
                    return flow_type(src[1])
                if kind == "d_type_ex":
                    return flow_type(src[1], _cmp_mu(src[2]))
                if kind == "d_ids":
                    return flow_ids(_cmp_mu(src[1]))
                if kind == "map":
                    return flow_ids(cmp_cf_div)
                if kind == "capex":
                    return flow_type(("asset_fixed",)) - pl["depreciation"]
                if kind == "invest_other":
                    return (flow_type(("asset_non_current",),
                                      cmp_cf_invest_other)
                            + flow_ids(cmp_cf_invest_other))
                if kind == "wc_other":
                    return (flow_type(CF_OTHER_CA_TYPES,
                                      set(shared["inv_ids"]))
                            + flow_type(CF_OTHER_CL_TYPES, cmp_cf_carveout))
                if kind == "equity_fin":
                    return (flow_type(EQUITY_TYPES, cmp_cf_div)
                            + flow_type(CF_FIN_LIAB_TYPES, cmp_cf_carveout))
                return 0.0

            cf_col = {}
            cf_sec_run = defaultdict(float)
            for ckind, csec, ckey, _clabel, csrc in CF_WATERFALL:
                if ckind == "subtotal":
                    if csrc[0] == "lines":
                        v = cf_sec_run[csrc[1]]
                    else:
                        v = sum(cf_col[k] for k in csrc[1])
                    cf_col[ckey] = v
                    values[ckey].append(v)
                    continue
                v = cf_col_val(csrc)
                cf_col[ckey] = v
                values[ckey].append(v)
                cf_sec_run[csec] += v

            revenue = pl["revenue"]
            values["gp_pct"].append(
                round(pl["gross"] / revenue * 100.0, 1) if revenue else None)
            values["ebitda_pct"].append(
                round(pl["ebitda"] / revenue * 100.0, 1) if revenue else None)
            values["net_pct"].append(
                round(pl["net"] / revenue * 100.0, 1) if revenue else None)

        return values

    def _build_compare(self, f, shared):
        """ตารางเปรียบเทียบหลายงวด: P&L สรุป + งบดุลย่อ + KPI ต่อคอลัมน์

        P&L = ยอดไหลในหน้าต่างคอลัมน์, งบดุล = ยอดสะสม ณ วันสิ้นคอลัมน์,
        delta_pct เทียบคอลัมน์ก่อนหน้า (ใช้ _yoy จึงคืน None เมื่อฐานเป็นศูนย์
        แทนที่จะปลอม %) ปิดอยู่ = ไม่ยิงคิวรีเพิ่มแม้แต่ครั้งเดียว
        """
        result = {
            "enabled": bool(f["compare_mode"]),
            "mode": f["compare_mode"] or "month",
            "count": f["compare_count"],
            "columns": [],
            "pnl_rows": [],
            "bs_rows": [],
            "cf_rows": [],
            "kpi_rows": [],
            "ebitda_configured": shared["ebitda_configured"],
        }
        windows = self._compare_windows(f)
        if not windows:
            return result

        cfg_map = shared["cfg_map"]

        maps = self._waterfall_maps(shared)
        cmp_map_ids = maps["map_ids"]
        cmp_distributed = maps["distributed"]
        cmp_bs_map = maps["bs_map"]
        cmp_bs_all = maps["bs_all"]
        cmp_eq_mapped = maps["eq_mapped"]
        cmp_cf_div = maps["cf_div"]
        cmp_cf_invest_other = maps["cf_invest_other"]
        cmp_cf_carveout = maps["cf_carveout"]

        def _cmp_mu(keys):
            return self._bs_map_union(cmp_bs_map, keys)

        def cmp_drill(src):
            """(types, account_ids, exclude_ids) สำหรับ openCmpCell ฝั่งจอ (P&L)"""
            if src is None:
                return [], [], []
            if src[0] == "map":
                return [], sorted(cmp_map_ids[src[1]]), []
            if src[0] == "type_ex":
                return list(src[1]), [], sorted(cmp_distributed)
            return list(src[1]), [], []

        def cmp_bs_drill(src):
            """(types, account_ids, exclude_ids) ของบรรทัดงบดุล"""
            if src[0] == "map":
                return [], sorted(cmp_bs_map.get(src[1], ())), []
            if src[0] == "type_ex":
                return list(src[1]), [], sorted(cmp_bs_all)
            if src[0] == "equity_plug":
                return (list(EQUITY_TYPES) + list(PL_TYPES), [],
                        sorted(cmp_eq_mapped))
            return list(src[1]), [], []

        def cmp_cf_drill(src):
            return self._cf_drill(shared, maps, src)

        kpi_defs = [
            ("gp_pct", _("อัตรากำไรขั้นต้น %")),
            ("ebitda_pct", _("อัตรา EBITDA %")),
            ("net_pct", _("อัตรากำไรสุทธิ %")),
            ("revenue_growth_pct", _("รายได้เติบโต % (เทียบคอลัมน์ก่อน)")),
        ]
        values = self._waterfall_columns(
            f, shared, cfg_map, windows, maps)

        def money(series):
            return [round(v, 2) or 0.0 for v in series]

        def deltas(series):
            out = [None]
            for index in range(1, len(series)):
                out.append(self._yoy(series[index], series[index - 1]))
            return out

        values["revenue_growth_pct"] = deltas(values["revenue"])

        result["columns"] = [
            {k: v for k, v in col.items() if not k.startswith("_")}
            for col in windows
        ]
        pnl_rows = []
        for kind, key, label, _sign, src in PNL_WATERFALL:
            types, account_ids, exclude_ids = cmp_drill(src)
            configured = bool(account_ids) if src and src[0] == "map" else True
            pnl_rows.append({
                "key": key, "label": label, "kind": kind,
                "types": types, "account_ids": account_ids,
                "exclude_ids": exclude_ids, "cumulative": False,
                "good_when_up": key in COMPARE_GOOD_WHEN_UP,
                "configured": configured,
                "values": money(values[key]),
                "delta_pct": deltas(values[key]),
            })
        result["pnl_rows"] = pnl_rows
        bs_rows = []
        for kind, sec, key, label, src in BS_WATERFALL:
            if kind == "subtotal":
                types, account_ids, exclude_ids, configured = [], [], [], True
            else:
                types, account_ids, exclude_ids = cmp_bs_drill(src)
                configured = (bool(account_ids) if src[0] == "map" else True)
            bs_rows.append({
                "key": key, "label": label, "kind": kind, "sec": sec,
                "types": types, "account_ids": account_ids,
                "exclude_ids": exclude_ids, "cumulative": True,
                "configured": configured,
                "good_when_up": key in COMPARE_GOOD_WHEN_UP,
                "values": money(values[key]),
                "delta_pct": deltas(values[key]),
            })
        result["bs_rows"] = bs_rows
        cf_rows = []
        for kind, sec, key, label, src in CF_WATERFALL:
            if kind == "subtotal":
                types, account_ids, exclude_ids, configured = [], [], [], True
            else:
                types, account_ids, exclude_ids = cmp_cf_drill(src)
                configured = (bool(account_ids) if src[0] == "map" else True)
            cf_rows.append({
                "key": key, "label": label, "kind": kind, "sec": sec,
                "types": types, "account_ids": account_ids,
                "exclude_ids": exclude_ids, "cumulative": False,
                # กระแสเงินสด: ตัวเลขบวก = เงินเข้า = ดีเสมอ
                "good_when_up": True, "configured": configured,
                "values": money(values[key]),
                "delta_pct": deltas(values[key]),
            })
        result["cf_rows"] = cf_rows
        result["kpi_rows"] = [
            {"key": key, "label": label, "unit": "pct",
             "values": values[key]}
            for key, label in kpi_defs
        ]
        return result

    # ------------------------------------------------------------------
    # Sales Channel (วิเคราะห์ช่องทางขาย) — P&L รายเดือนแยกช่องทาง
    # ------------------------------------------------------------------
    def _channel_columns(self, f):
        """คอลัมน์ของแท็บช่องทางขาย = งวดรายเดือนของปีงบ ถึงงวดที่เลือกใน toolbar

        ใช้ `_fy_periods` ตัวเดียวกับ toolbar/Statements จึงรองรับปีงบที่ไม่ตรง
        ปฏิทินอัตโนมัติ — **ห้ามใช้ `_month_grid`** นั่นเป็นกริด *อนาคต* ของ
        แท็บ Forecast (เริ่มนับจากวันนี้ + มีคอลัมน์ "หลังจากนี้")
        """
        columns = []
        for period in self._fy_periods(f["fy_start"], f["fy_end"]):
            if period["date_from"] > f["as_of"]:
                break
            date_to = min(period["date_to"], f["as_of"])
            columns.append({
                "index": len(columns),
                "label": period["label"],
                "date_from": str(period["date_from"]),
                "date_to": str(date_to),
                # openCmpCell ใช้ as_of กับแถวยอดสะสม — ที่นี่ทุกแถวเป็นยอดไหล
                "as_of": str(date_to),
                "_from": period["date_from"],
                "_to": date_to,
            })
        return columns

    def _pnl_account_ids(self, maps, src):
        """บัญชีของบรรทัด P&L หนึ่งบรรทัด

        สูตรเดียวกับ `pnl_src_ids` ใน `_build_statements` — ที่มาเดียวกันคือ
        ช่อง src ของ `PNL_WATERFALL` (อย่าตีความ src ที่อื่นอีก)
        """
        kind, arg = src
        if kind == "map":
            return sorted(maps["map_ids"][arg])
        ids = [a for t in arg for a in maps["by_type"].get(t, ())]
        if kind == "type_ex":
            ids = [a for a in ids if a not in maps["distributed"]]
        return ids

    def _channel_domain(self, f):
        """โดเมน journal item ฝั่ง P&L ของปีงบถึง as_of (ฐานของทุกคิวรีในแท็บนี้)"""
        return [
            ("parent_state", "=", "posted"),
            ("company_id", "in", f["cids"]),
            ("account_id.account_type", "in", list(PL_TYPES)),
            ("date", ">=", str(f["fy_start"])),
            ("date", "<=", str(f["as_of"])),
        ]

    def _channel_facts(self, f, shared, columns, dim):
        """ยอด P&L รายเดือนสามชั้น: ระดับบริษัท / ต่อช่องทาง / ต่อสาขา

        ชั้นช่องทางกับสาขาเก็บเฉพาะยอดที่ **ผูกมิติได้จาก GL จริง** ส่วนต่างกับ
        ชั้นบริษัทคือ "กองที่รอเฉลี่ย" ซึ่ง `_build_channel` เป็นคนปัน

        **กับดักที่ต้องรู้:** `account.move.line.partner_id` ของ core คือ
        *commercial partner* — สาขาถูกยุบเป็นบริษัทแม่ตั้งแต่ตอนโพสต์ ชั้น
        "ช่องทาง" จึงอ่านจากบรรทัดได้ตรง ๆ แต่ชั้น "สาขา" ต้องกางจากหัวเอกสาร
        (`account.move.partner_id`) เสมอ — และทำเฉพาะบัญชีรายได้ ไม่งั้นต้อง
        จัดกลุ่มรายเอกสารทั้งฝั่ง P&L ซึ่งแพงเกินความจำเป็น

        เครื่องหมายตามหน้างบ (เหมือน PNL_WATERFALL): รายได้เป็นบวก
        ต้นทุน/ค่าใช้จ่ายเป็นบวก และแปลงค่าเงินด้วย **อัตราของคอลัมน์นั้น**
        (closing rate ณ วันสิ้นเดือน) เพื่อให้บวกกันแล้วเท่ากับยอดของ
        `_waterfall_columns` เป๊ะ
        """
        acc_type = shared["acc_type"]
        acc_company = shared["acc_company"]
        col_of_month = {}
        rates = {}
        for col in columns:
            col_of_month[(col["_from"].year, col["_from"].month)] = col["index"]
            rates[col["index"]] = self._fx_rates_memo(
                shared, f["cids"], col["_to"], f["presentation_currency"])

        account = defaultdict(float)
        direct = defaultdict(float)
        branch = defaultdict(float)
        names, branch_names = {}, {}
        domains, branch_domains = {}, {}

        def value_of(account_id, day, balance):
            """(index ของคอลัมน์, ยอดตามหน้างบ) — None ถ้าเดือนนั้นไม่มีคอลัมน์"""
            index = col_of_month.get((day.year, day.month))
            if index is None or not balance:
                return None, 0.0
            sign = -1.0 if acc_type.get(account_id) in REVENUE_TYPES else 1.0
            return index, sign * balance * rates[index].get(
                acc_company.get(account_id), 1.0)

        AML = self.env["account.move.line"]
        base = self._channel_domain(f)

        # ---- ชั้นบริษัท (1 คิวรี) — ฐานของแถว "ประเภทต้นทุน" และของส่วนต่าง ----
        for acc, day, balance in AML._read_group(
                base, groupby=["account_id", "date:month"],
                aggregates=["balance:sum"]):
            index, amount = value_of(acc.id, day, balance)
            if index is not None:
                account[(acc.id, index)] += amount

        def add_split(channel, acc_id, day, balance):
            index, amount = value_of(acc_id, day, balance)
            if index is not None and channel:
                direct[(channel, acc_id, index)] += amount

        # ---- ชั้นช่องทาง ----
        if dim == "team":
            teams = self.env["crm.team"].search([
                "|", ("company_id", "=", False),
                ("company_id", "in", f["cids"]),
            ])
            # team_id อยู่บน account.move (โมดูล sale) ไม่ใช่บรรทัด จึง group
            # ตรงไม่ได้ — ยิงทีมละคิวรี (จำนวนทีมมีหลักหน่วยถึงหลักสิบ)
            # เอกสารที่ไม่มีทีมไม่ต้องยิงเลย: มันคือ "กองที่รอเฉลี่ย" อยู่แล้ว
            for team in teams:
                rows = AML._read_group(
                    base + [("move_id.team_id", "=", team.id)],
                    groupby=["account_id", "date:month"],
                    aggregates=["balance:sum"])
                if not rows:
                    continue
                names[team.id] = team.name
                domains[team.id] = [("move_id.team_id", "=", team.id)]
                for acc, day, balance in rows:
                    add_split(team.id, acc.id, day, balance)
        elif dim == "analytic":
            plan = (self.env["account.analytic.plan"].browse(f["plan_id"])
                    if f["plan_id"] else self._controlling_plans()[:1])
            analytic = self.env["account.analytic.account"].search(
                [("plan_id", "child_of", plan.id)]) if plan \
                else self.env["account.analytic.account"]
            allowed = {a.id: a.name for a in analytic}
            lines = AML.search_read(
                base + [("analytic_distribution", "!=", False)],
                ["account_id", "date", "balance", "analytic_distribution"],
            ) if allowed else []
            for line in lines:
                acc_id = line["account_id"][0] if line["account_id"] else 0
                if not acc_id:
                    continue
                # jsonb {"12": 100.0} หรือ {"12,34": 100.0} — คีย์ที่มีคอมมาคือ
                # กระจายข้ามหลายแผนพร้อมกัน แต่ละ id ได้ % เต็มของแผนตัวเอง
                for raw_key, percent in (
                        line["analytic_distribution"] or {}).items():
                    for raw_id in str(raw_key).split(","):
                        try:
                            analytic_id = int(raw_id)
                        except ValueError:
                            continue
                        if analytic_id not in allowed:
                            continue
                        add_split(
                            analytic_id, acc_id, line["date"],
                            (line["balance"] or 0.0) * (percent or 0.0) / 100.0)
                        names[analytic_id] = allowed[analytic_id]
                        domains[analytic_id] = [
                            ("analytic_distribution", "in", [analytic_id])]
        else:   # partner — ช่องทาง = ลูกค้าเชน (commercial partner)
            rows = AML._read_group(
                base, groupby=["partner_id", "account_id", "date:month"],
                aggregates=["balance:sum"])
            partner_ids = {p.id for p, _a, _d, _b in rows if p}
            chain_of, chain_name = {}, {}
            for row in self.env["res.partner"].search_read(
                    [("id", "in", list(partner_ids))],
                    ["commercial_partner_id", "display_name"]):
                commercial = row["commercial_partner_id"]
                chain_id = commercial[0] if commercial else row["id"]
                chain_of[row["id"]] = chain_id
                chain_name[chain_id] = (
                    commercial[1] if commercial else row["display_name"])
            for partner, acc, day, balance in rows:
                if not partner:
                    continue
                channel = chain_of.get(partner.id, partner.id)
                add_split(channel, acc.id, day, balance)
                names[channel] = chain_name.get(channel, partner.display_name)
                # partner_id ของบรรทัด = commercial partner อยู่แล้ว จึงกรอง
                # ด้วยค่าเดียวได้ ไม่ต้องไล่ลูกทุกตัว
                domains[channel] = [("partner_id", "=", channel)]

        # ---- ชั้นสาขา (บัญชีรายได้เท่านั้น — สาขาจริงอยู่บนหัวเอกสาร) ----
        rev_rows = AML._read_group(
            base + [("account_id.account_type", "in", list(REVENUE_TYPES))],
            groupby=["move_id", "account_id", "date:month"],
            aggregates=["balance:sum"],
        ) if names and dim in ("partner", "team") else []
        move_ids = {move.id for move, _a, _d, _b in rev_rows}
        move_info = {}
        if move_ids:
            fields_to_read = ["partner_id", "commercial_partner_id"]
            if "team_id" in self.env["account.move"]._fields:
                fields_to_read.append("team_id")
            for row in self.env["account.move"].search_read(
                    [("id", "in", list(move_ids))], fields_to_read):
                move_info[row["id"]] = row
        for move, acc, day, balance in rev_rows:
            info = move_info.get(move.id)
            if not info:
                continue
            if dim == "team":
                team = info.get("team_id")
                channel = team[0] if team else 0
            else:
                commercial = info.get("commercial_partner_id")
                channel = commercial[0] if commercial else 0
            if channel not in names:
                continue
            partner = info.get("partner_id")
            partner_id = partner[0] if partner else 0
            index, amount = value_of(acc.id, day, balance)
            if index is None:
                continue
            branch[(channel, partner_id, acc.id, index)] += amount
            branch_names[(channel, partner_id)] = (
                partner[1] if partner else _("ไม่ระบุสาขา"))
            branch_domains[(channel, partner_id)] = [
                ("move_id.partner_id", "=", partner_id or False)]

        return {
            "account": account,
            "direct": direct,
            "branch": branch,
            "names": names,
            "branch_names": branch_names,
            "domains": domains,
            "branch_domains": branch_domains,
        }

    def _build_channel(self, f, shared):
        """งบกำไรขาดทุนรายเดือนแยกช่องทางขาย

        **กติกาการปันยอด — GL จริงก่อน ที่เหลือเฉลี่ยตามรายได้:**

        * ยอดที่ผูกมิติช่องทางได้จาก GL = ยอดจริงของช่องทางนั้น (direct)
        * **รายได้ที่ผูกไม่ได้ไม่เฉลี่ย** — ค้างที่แถว "ไม่ระบุช่องทาง" เพราะ
          รายได้เป็นตัวหารของการเฉลี่ย เอามาเฉลี่ยตัวเองไม่ได้
        * ต้นทุน/ค่าใช้จ่ายที่ผูกไม่ได้ (SG&A ส่วนกลาง, บริษัทที่อ่าน GL จาก
          ระบบภายนอกซึ่งไม่มีมิติช่องทางเลย) เฉลี่ยเข้าทุกช่องทางตามสัดส่วน
          **รายได้ของเดือนนั้น** — เดือนที่ยังไม่มีรายได้ใช้สัดส่วนทั้งปีงบ
          ถ้ายังไม่มีอีกก็ค้างไว้ที่ "ไม่ระบุช่องทาง" (ห้ามหายเงียบ ๆ และห้าม
          เฉลี่ยเท่ากันทุกช่องทางแบบมั่ว ๆ)
        * **Invariant:** Σ ทุกช่องทางของบรรทัดหนึ่งในเดือนหนึ่ง = ยอดบรรทัด
          เดียวกันของงบระดับบริษัทที่ `_waterfall_columns` คิดไว้เสมอ

        แท็บนี้มีเฉพาะงบกำไรขาดทุน — งบกระแสเงินสดรายเดือน **ตัดออกตามที่ผู้ใช้
        สั่ง (2026-09-04)** เพราะแยกตามช่องทางไม่ได้อยู่แล้ว ใครอยากดูให้ไปที่
        แท็บ Statements หรือ Compare BI โหมดรายเดือน (ตัวเลขชุดเดียวกัน)
        """
        cfg_map = shared["cfg_map"]
        columns = self._channel_columns(f)
        maps = self._waterfall_maps(shared)
        values = self._waterfall_columns(f, shared, cfg_map, columns, maps)
        dim = f["channel_dim"]
        span = len(columns)
        facts = self._channel_facts(f, shared, columns, dim)

        def zero():
            return [0.0] * span

        # บัญชีของแต่ละบรรทัด — บัญชีหนึ่งอยู่ได้บรรทัดเดียว (first match)
        # ไม่งั้นบัญชีที่ถูก map ซ้ำสองช่องจะถูกนับสองรอบแล้ว invariant พัง
        row_accounts, row_of_account = {}, {}
        for kind, key, _label, _sign, src in PNL_WATERFALL:
            if kind != "line":
                continue
            ids = [a for a in self._pnl_account_ids(maps, src)
                   if a not in row_of_account]
            row_accounts[key] = ids
            for account_id in ids:
                row_of_account[account_id] = key

        channels = sorted(facts["names"])
        acc_total = facts["account"]

        # ---- ยอดที่ผูกช่องทางได้ (direct) ต่อบรรทัด / ต่อบัญชี ----
        direct_row = {(key, ch): zero()
                      for key in CHANNEL_PNL_LINES for ch in channels}
        direct_acc = defaultdict(zero)
        for (ch, account_id, index), amount in facts["direct"].items():
            key = row_of_account.get(account_id)
            if key is None or (key, ch) not in direct_row:
                continue
            direct_row[(key, ch)][index] += amount
            direct_acc[(ch, account_id)][index] += amount

        # ---- ส่วนที่ยังไม่มีเจ้าของ: รายบัญชี + ผลต่างระดับบรรทัด (plug) ----
        residual_acc = defaultdict(zero)
        for (account_id, index), amount in acc_total.items():
            if row_of_account.get(account_id) is None:
                continue
            owned = sum(direct_acc[(ch, account_id)][index] for ch in channels)
            residual_acc[account_id][index] += amount - owned
        residual_row = {}
        for key in CHANNEL_PNL_LINES:
            series = zero()
            for index in range(span):
                # บรรทัดสรุปย่อยอ่านจาก engine (sga เป็นตัวปิดของ opex) จึงอาจ
                # ไม่เท่าผลรวมรายบัญชีเป๊ะ — ส่วนต่างนี้ก็ต้องถูกปันเหมือนกัน
                by_account = sum(
                    acc_total.get((a, index), 0.0)
                    for a in row_accounts.get(key, ()))
                series[index] = values[key][index] - by_account + sum(
                    residual_acc[a][index] for a in row_accounts.get(key, ()))
            residual_row[key] = series

        # ---- รายได้ต่อช่องทาง = ฐานของการเฉลี่ย (รายได้ที่ผูกไม่ได้ค้างที่ 0) ----
        revenue = {ch: list(direct_row[("revenue_op", ch)]) for ch in channels}
        revenue[CHANNEL_NONE] = list(residual_row["revenue_op"])
        all_channels = channels + [CHANNEL_NONE]

        # สัดส่วนต่อเดือน (ฐานตัดยอดติดลบทิ้ง — ใบลดหนี้ไม่ควรดูดต้นทุนเข้าตัว)
        fy_base = {ch: max(sum(revenue[ch]), 0.0) for ch in all_channels}
        fy_total = sum(fy_base.values())
        shares = []
        for index in range(span):
            month = {ch: max(revenue[ch][index], 0.0) for ch in all_channels}
            total = sum(month.values())
            if total:
                shares.append({ch: v / total for ch, v in month.items() if v})
            elif fy_total:
                shares.append({ch: v / fy_total
                               for ch, v in fy_base.items() if v})
            else:
                shares.append({})

        def allocate(series):
            """ปัน residual ต่อเดือนตามสัดส่วนรายได้ — ช่องสุดท้ายรับเศษ
            เพื่อให้ Σ ที่ปันแล้ว = residual เป๊ะทุกเดือน"""
            out = defaultdict(zero)
            for index in range(span):
                amount = series[index]
                if not amount:
                    continue
                weights = shares[index]
                if not weights:
                    out[CHANNEL_NONE][index] += amount
                    continue
                items = sorted(weights.items())
                running = 0.0
                for position, (ch, fraction) in enumerate(items):
                    part = (amount - running if position == len(items) - 1
                            else round(amount * fraction, 2))
                    out[ch][index] += part
                    running += part
            return out

        alloc_row = {key: allocate(residual_row[key])
                     for key in CHANNEL_PNL_LINES if key != "revenue_op"}

        def line_series(key, ch):
            """ยอดบรรทัดหนึ่งของช่องทางหนึ่ง = direct + ส่วนที่เฉลี่ยมา"""
            if key == "revenue_op":
                return list(revenue[ch])
            base = (direct_row.get((key, ch)) or zero())
            extra = alloc_row[key].get(ch) or zero()
            return [base[i] + extra[i] for i in range(span)]

        # ---- ตารางเทียบช่องทาง (แถว = ช่องทาง, คอลัมน์ = เดือน) ----
        def totals_of(line_values):
            out = dict(line_values)
            for key, formula in CHANNEL_PNL_TOTALS.items():
                out[key] = [
                    sum(sign * out[src][i] for src, sign in formula)
                    for i in range(span)
                ]
            return out

        per_channel = {}
        for ch in all_channels:
            per_channel[ch] = totals_of(
                {key: line_series(key, ch) for key in CHANNEL_PNL_LINES})

        def pct_series(numerator, denominator):
            return [
                round(numerator[i] / denominator[i] * 100.0, 1)
                if denominator[i] else None
                for i in range(span)
            ]

        matrix_rows = []
        for ch in all_channels:
            data = per_channel[ch]
            if not any(abs(v) > 0.005 for key in data for v in data[key]):
                continue
            matrix_rows.append({
                "key": ch,
                "name": facts["names"].get(ch, _("ไม่ระบุช่องทาง")),
                "drillable": bool(facts["domains"].get(ch)),
                "metrics": {
                    "revenue": [round(v, 2) or 0.0 for v in data["revenue_op"]],
                    "cogs": [round(v, 2) or 0.0 for v in data["cogs"]],
                    "gross": [round(v, 2) or 0.0 for v in data["gross_op"]],
                    "gross_pct": pct_series(
                        data["gross_op"], data["revenue_op"]),
                    "sga": [round(v, 2) or 0.0 for v in data["sga"]],
                    "ebit": [round(v, 2) or 0.0 for v in data["ebit"]],
                },
                "totals": {
                    "revenue": round(sum(data["revenue_op"]), 2) or 0.0,
                    "cogs": round(sum(data["cogs"]), 2) or 0.0,
                    "gross": round(sum(data["gross_op"]), 2) or 0.0,
                    "gross_pct": round(
                        sum(data["gross_op"]) / sum(data["revenue_op"]) * 100.0,
                        1) if sum(data["revenue_op"]) else None,
                    "sga": round(sum(data["sga"]), 2) or 0.0,
                    "ebit": round(sum(data["ebit"]), 2) or 0.0,
                },
            })
        matrix_rows.sort(key=lambda r: -r["totals"]["revenue"])
        if len(matrix_rows) > CHANNEL_MAX_ROWS:
            tail = matrix_rows[CHANNEL_MAX_ROWS:]
            matrix_rows = matrix_rows[:CHANNEL_MAX_ROWS]
            merged = {
                "key": -1,
                "name": _("อื่น ๆ (%s ช่องทาง)") % len(tail),
                "drillable": False,
                "metrics": {}, "totals": {},
            }
            for metric in ("revenue", "cogs", "gross", "sga", "ebit"):
                merged["metrics"][metric] = [
                    round(sum(r["metrics"][metric][i] for r in tail), 2) or 0.0
                    for i in range(span)
                ]
                merged["totals"][metric] = round(
                    sum(r["totals"][metric] for r in tail), 2) or 0.0
            merged["metrics"]["gross_pct"] = pct_series(
                merged["metrics"]["gross"], merged["metrics"]["revenue"])
            merged["totals"]["gross_pct"] = round(
                merged["totals"]["gross"] / merged["totals"]["revenue"] * 100.0,
                1) if merged["totals"]["revenue"] else None
            matrix_rows.append(merged)

        # ---- ขอบเขตของงบ: ทุกช่องทาง (0) หรือช่องทางเดียว ----
        channel_id = f["channel_id"]
        if channel_id and channel_id not in per_channel:
            channel_id = 0
        scope = per_channel[channel_id] if channel_id else totals_of(
            {key: list(values[key]) for key in CHANNEL_PNL_LINES})
        scope_domain = facts["domains"].get(channel_id) or []

        def sub_rows(key):
            """แถวย่อยของบรรทัด — รายได้กางเป็นช่องทาง/สาขา ต้นทุนกางเป็นบัญชี"""
            rows = []
            if key == "revenue_op" and not channel_id:
                for row in matrix_rows:
                    rows.append({
                        "key": "ch-%s" % row["key"],
                        "name": row["name"],
                        "values": row["metrics"]["revenue"],
                        "total": row["totals"]["revenue"],
                        "extra_domain": facts["domains"].get(row["key"]) or None,
                    })
                return rows
            if key == "revenue_op":
                bucket = defaultdict(zero)
                for (ch, partner_id, account_id, index), amount in \
                        facts["branch"].items():
                    if ch == channel_id and account_id in row_accounts[key]:
                        bucket[partner_id][index] += amount
                for partner_id, series in bucket.items():
                    rows.append({
                        "key": "br-%s" % partner_id,
                        "name": facts["branch_names"].get(
                            (channel_id, partner_id), _("ไม่ระบุสาขา")),
                        "values": [round(v, 2) or 0.0 for v in series],
                        "total": round(sum(series), 2) or 0.0,
                        "extra_domain": facts["branch_domains"].get(
                            (channel_id, partner_id)) or None,
                    })
                rows.sort(key=lambda r: -r["total"])
                rows = rows[:CHANNEL_MAX_SUB_ROWS - 1]
                # partner_id ของบรรทัดกับของหัวเอกสารอาจไม่ตรงกัน (แก้มือ) —
                # ส่วนต่างต้องเห็น ไม่ใช่หายไปจากงบของช่องทางนี้
                gap = [
                    scope[key][i] - sum(r["values"][i] for r in rows)
                    for i in range(span)
                ]
                if any(abs(v) > 0.005 for v in gap):
                    rows.append({
                        "key": "gap-%s" % key,
                        "name": _("สาขาอื่น ๆ / ยอดที่ไม่ระบุสาขา"),
                        "values": [round(v, 2) or 0.0 for v in gap],
                        "total": round(sum(gap), 2) or 0.0,
                        "extra_domain": None,
                    })
                return rows
            # ต้นทุน / ค่าใช้จ่าย: แถวย่อย = บัญชี ("ประเภทต้นทุน" ในเวิร์กชีต)
            acc_name = shared["acc_name"]
            acc_code = shared["acc_code"]
            alloc_cache = {}
            for account_id in row_accounts.get(key, ()):
                if channel_id:
                    allocated = alloc_cache.get(account_id)
                    if allocated is None:
                        allocated = allocate(residual_acc[account_id])
                        alloc_cache[account_id] = allocated
                    base = direct_acc[(channel_id, account_id)]
                    extra = allocated.get(channel_id) or zero()
                    series = [base[i] + extra[i] for i in range(span)]
                    alloc_series = list(extra)
                else:
                    series = [acc_total.get((account_id, i), 0.0)
                              for i in range(span)]
                    alloc_series = zero()
                if all(abs(v) < 0.005 for v in series):
                    continue
                rows.append({
                    "key": "ac-%s" % account_id,
                    "name": acc_name.get(account_id, "?"),
                    "code": acc_code.get(account_id, ""),
                    "values": [round(v, 2) or 0.0 for v in series],
                    "total": round(sum(series), 2) or 0.0,
                    "allocated": [round(v, 2) or 0.0 for v in alloc_series],
                    "account_ids": [account_id],
                    "extra_domain": scope_domain or None,
                })
            # ตัดจำนวนแถวก่อนคิดส่วนต่าง — บัญชีที่ถูกตัดออกต้องถูกกลืนเข้า
            # แถวปิดท้าย ไม่ใช่หายไปจนแถวย่อยบวกไม่เท่าบรรทัดแม่
            rows.sort(key=lambda r: -abs(r["total"]))
            rows = rows[:CHANNEL_MAX_SUB_ROWS - 1]
            rows.sort(key=lambda r: r.get("code") or "")
            # ผลต่างระหว่างยอดบรรทัด (engine) กับผลรวมรายบัญชี — ต้องเห็น
            gap = [
                scope[key][i] - sum(r["values"][i] for r in rows)
                for i in range(span)
            ]
            if any(abs(v) > 0.005 for v in gap):
                rows.append({
                    "key": "gap-%s" % key,
                    "name": _("บัญชีอื่น ๆ / ยอดที่ยังไม่ระบุบัญชี"),
                    "code": "zzz",
                    "values": [round(v, 2) or 0.0 for v in gap],
                    "total": round(sum(gap), 2) or 0.0,
                    "allocated": [round(v, 2) or 0.0 for v in gap],
                    "extra_domain": None,
                })
            return rows

        pnl_rows = []
        for kind, key, label, sub in CHANNEL_PNL:
            if kind == "pct":
                series = pct_series(scope[sub], scope["revenue_op"])
                total_rev = sum(scope["revenue_op"])
                pnl_rows.append({
                    "key": key, "label": label, "kind": "pct",
                    "values": series,
                    "total": round(sum(scope[sub]) / total_rev * 100.0, 1)
                    if total_rev else None,
                    "sub": [],
                })
                continue
            series = scope[key]
            row = {
                "key": key, "label": label, "kind": kind,
                "values": [round(v, 2) or 0.0 for v in series],
                "total": round(sum(series), 2) or 0.0,
                "pct_of_revenue": pct_series(series, scope["revenue_op"]),
                "sub": sub_rows(key) if kind == "split" else [],
                "types": [], "account_ids": [], "exclude_ids": [],
                "extra_domain": scope_domain or None,
            }
            if kind == "split":
                if key not in alloc_row:            # รายได้ไม่มีการเฉลี่ย
                    allocated = zero()
                elif channel_id:
                    allocated = alloc_row[key].get(channel_id) or zero()
                else:
                    allocated = residual_row[key]
                row["allocated"] = [round(v, 2) or 0.0 for v in allocated]
                row["account_ids"] = row_accounts.get(key, [])
            pnl_rows.append(row)

        # ---- ความโปร่งใสของการเฉลี่ย ----
        # รวมแบบ **ค่าสัมบูรณ์รายเดือน** ไม่ใช่ผลรวมตรง ๆ — ยอดบวก/ลบข้ามเดือน
        # (ใบลดหนี้, กลับรายการ) หักกันจนเหลือศูนย์แล้วจอจะรายงานว่า
        # "ไม่มีการเฉลี่ยเลย" ทั้งที่เฉลี่ยไปทั้งปี
        direct_total = sum(
            abs(sum(direct_row[(key, ch)][index] for ch in channels))
            for key in CHANNEL_PNL_LINES for index in range(span))
        allocated_total = sum(
            abs(residual_row[key][index]) for key in CHANNEL_PNL_LINES
            if key != "revenue_op" for index in range(span))
        unassigned_revenue = sum(
            abs(v) for v in residual_row["revenue_op"])
        return {
            "dims": [{"code": code, "label": label, "sub_label": sub}
                     for code, label, sub in CHANNEL_DIMS],
            "dim": dim,
            "dim_label": dict(
                (code, label) for code, label, _s in CHANNEL_DIMS)[dim],
            "sub_label": dict(
                (code, sub) for code, _l, sub in CHANNEL_DIMS)[dim],
            "channel_id": channel_id,
            "channel_label": facts["names"].get(channel_id, "")
            if channel_id else _("ทุกช่องทาง"),
            "channels": [
                {"key": row["key"], "name": row["name"],
                 "revenue": row["totals"]["revenue"],
                 "drillable": row["drillable"]}
                for row in matrix_rows if row["key"] >= 0
            ],
            "columns": [
                {k: v for k, v in col.items() if not k.startswith("_")}
                for col in columns
            ],
            "matrix": {
                "metrics": [
                    {"code": "revenue", "label": _("รายได้"), "unit": "money"},
                    {"code": "cogs", "label": _("ต้นทุนขาย"), "unit": "money"},
                    {"code": "gross", "label": _("กำไรขั้นต้น"),
                     "unit": "money"},
                    {"code": "gross_pct", "label": _("อัตรากำไรขั้นต้น %"),
                     "unit": "pct"},
                    {"code": "sga", "label": _("SG&A"), "unit": "money"},
                    {"code": "ebit", "label": _("EBIT"), "unit": "money"},
                ],
                "rows": matrix_rows,
            },
            "pnl_rows": pnl_rows,
            "alloc": {
                "direct": round(direct_total, 2) or 0.0,
                "allocated": round(allocated_total, 2) or 0.0,
                "unassigned_revenue": round(unassigned_revenue, 2) or 0.0,
                "basis": "revenue",
            },
        }

    # ------------------------------------------------------------------
    # Financial Statements (สไตล์ SAP F.01) — BS / P&L / Cash Flow / AR aging
    # ------------------------------------------------------------------
    def _build_statements(self, f, shared):
        """งบการเงินเชิงโครงสร้าง เทียบงวดก่อน พร้อมแถวรายบัญชีให้ drill

        * Balance Sheet: ยอดสะสม ณ as_of เทียบ as_of_prior จัดกลุ่มตาม
          account_type — ส่วนของผู้ถือหุ้นเติมแถว "กำไรสะสมระหว่างปี" จาก
          ยอด P&L สะสมที่ยังไม่ปิดงวด งบจึงดุลเสมอ (check = ส่วนต่างที่เหลือ
          เช่นบัญชี off_balance — โชว์เตือนเมื่อไม่เป็นศูนย์)
        * P&L: waterfall YTD เทียบ prior-YTD (Revenue → Gross → SG&A →
          Other income → EBITDA → D&A → EBIT → Interest → ก่อนภาษี → Tax → Net)
          บรรทัด line กางรายบัญชีได้ บรรทัด total อ่านจากถังของ engine
        * Cash Flow ทางอ้อม: Δ ยอดสะสมจากยกมาต้นงวด — identity ปิดที่
          asset_cash (ค่าเสื่อมบวกกลับใน operating แล้วหักคืนใน investing)
        * AR aging: ถังเดียวกับ AP (นับจากวันนี้) + รายลูกค้า
        """
        acc_by_type = defaultdict(list)
        for account_id, atype in shared["acc_type"].items():
            acc_by_type[atype].append(account_id)
        acc_code = shared["acc_code"]
        acc_name = shared["acc_name"]

        def pair_row(key, label, cur, prior, types=None):
            # `or 0.0` ล้าง -0.0 ของ Python — ไม่งั้น JS โชว์ "-0.0" เต็มตาราง
            return {
                "key": key,
                "label": label,
                "types": list(types) if types else [],
                "amount": round(cur, 2) or 0.0,
                "prior": round(prior, 2) or 0.0,
                "delta": round(cur - prior, 2) or 0.0,
                "delta_pct": self._yoy(cur, prior),
            }

        def account_rows(account_ids, cur_key, prior_key, sign):
            rows = []
            for account_id in account_ids:
                cur = sign * shared[cur_key].get(account_id, 0.0)
                prior = sign * shared[prior_key].get(account_id, 0.0)
                if abs(cur) < 0.005 and abs(prior) < 0.005:
                    continue
                rows.append(dict(
                    pair_row(str(account_id), acc_name[account_id],
                             cur, prior),
                    account_id=account_id,
                    code=acc_code[account_id],
                    # บัญชีภายนอก (คีย์ลบ) ไม่มีเอกสารต้นทางใน Odoo —
                    # จอต้องเช็คก่อนคลิก drill ลง journal item
                    drillable=account_id > 0,
                ))
            rows.sort(key=lambda r: r["code"])
            return rows

        # บัญชีที่ผูกไว้ใน config สำหรับบรรทัด waterfall (ค่าเสื่อม/ดอกเบี้ย/ภาษี)
        pnl_map_ids = {
            "dep": set(shared["dep_ids"])
            | set(acc_by_type.get("expense_depreciation", ())),
            "int": set(shared["int_ids"]),
            "tax": set(shared["tax_ids"]),
        }
        pnl_distributed = (
            pnl_map_ids["dep"] | pnl_map_ids["int"] | pnl_map_ids["tax"])

        def pnl_src_ids(src):
            kind, arg = src
            if kind == "map":
                return sorted(pnl_map_ids[arg])
            ids = [a for t in arg for a in acc_by_type.get(t, ())]
            if kind == "type_ex":
                ids = [a for a in ids if a not in pnl_distributed]
            return ids

        # ---- Balance Sheet แบบ waterfall (หมุนเวียน/ไม่หมุนเวียน + subtotal) ----
        bs_map_ids = shared["bs_map_ids"]
        bs_all_mapped = set().union(*bs_map_ids.values()) if bs_map_ids else set()
        # equity ที่ไม่ถูก map ไป "ทุนชำระแล้ว"/"สำรองตามกฎหมาย"
        eq_mapped = (bs_map_ids.get("paid_in_capital", set())
                     | bs_map_ids.get("legal_reserve", set()))
        eq_other_ids = [
            a for a in acc_by_type.get("equity", ()) if a not in eq_mapped
        ] + list(acc_by_type.get("equity_unaffected", ()))

        def bs_src_ids(src):
            if src[0] == "map":
                return sorted(bs_map_ids.get(src[1], ()))
            ids = [a for t in src[1] for a in acc_by_type.get(t, ())]
            if src[0] == "type_ex":
                ids = [a for a in ids if a not in bs_all_mapped]
            return ids

        bs_rows = []
        sec_sum = defaultdict(lambda: [0.0, 0.0])   # sec → [Σ amount, Σ prior]
        sub_by_key = {}
        for kind, sec, key, label, src in BS_WATERFALL:
            if kind == "subtotal":
                if src[0] == "lines":
                    cur, prior = sec_sum[src[1]]
                else:  # ผลรวมของบรรทัดสรุปที่ระบุ
                    cur = sum(sub_by_key[k]["amount"] for k in src[1])
                    prior = sum(sub_by_key[k]["prior"] for k in src[1])
                row = pair_row(key, label, cur, prior)
                row.update(kind="subtotal", sec=sec, accounts=[])
                bs_rows.append(row)
                sub_by_key[key] = row
                continue
            sign = BS_SEC_SIGN[sec]
            if src[0] == "equity_plug":
                # กำไรสะสม = equity ที่เหลือ + กำไร(ขาดทุน)สะสมระหว่างปี (−Σ P&L)
                accounts = account_rows(
                    eq_other_ids, "bal_cum", "bal_cum_prior", sign)
                cur = (sum(r["amount"] for r in accounts)
                       - self._sum_type(shared, "bal_cum", PL_TYPES))
                prior = (sum(r["prior"] for r in accounts)
                         - self._sum_type(shared, "bal_cum_prior", PL_TYPES))
                row = pair_row(key, label, cur, prior)
                row.update(
                    kind="line", sec=sec, accounts=accounts, configured=True,
                    types=list(EQUITY_TYPES) + list(PL_TYPES),
                    account_ids=[], exclude_ids=sorted(eq_mapped))
            else:
                ids = bs_src_ids(src)
                accounts = account_rows(
                    ids, "bal_cum", "bal_cum_prior", sign)
                cur = sum(r["amount"] for r in accounts)
                prior = sum(r["prior"] for r in accounts)
                row = pair_row(key, label, cur, prior)
                row.update(
                    kind="line", sec=sec, accounts=accounts,
                    configured=bool(ids) if src[0] == "map" else True)
                if src[0] == "map":
                    row.update(types=[], account_ids=ids, exclude_ids=[])
                else:
                    row.update(
                        types=list(src[1]), account_ids=[],
                        exclude_ids=(sorted(bs_all_mapped)
                                     if src[0] == "type_ex" else []))
            bs_rows.append(row)
            sec_sum[sec][0] += cur
            sec_sum[sec][1] += prior
        bs_check = round(
            sub_by_key["total_assets"]["amount"]
            - sub_by_key["total_liab_eq"]["amount"], 2)

        # ---- P&L แบบ waterfall (Revenue → … → Net income) ----
        pl = shared["pl_ytd"]["total"]
        plp = shared["pl_prior"]["total"]

        def pct_of_rev(value, revenue):
            return round(value / revenue * 100.0, 1) if revenue else None

        pnl_rows = []
        for kind, key, label, sign, src in PNL_WATERFALL:
            if kind == "total":
                row = pair_row(key, label, pl[key], plp[key])
                row["kind"] = "total"
                row["accounts"] = []
                row["pct_of_revenue"] = pct_of_rev(pl[key], pl["revenue"])
                row["prior_pct_of_revenue"] = pct_of_rev(
                    plp[key], plp["revenue"])
                pnl_rows.append(row)
                continue
            ids = pnl_src_ids(src)
            accounts = account_rows(ids, "bal_ytd", "bal_prior_ytd", sign)
            # บรรทัดสรุปย่อยอ่านจากถังของ engine โดยตรง (ครอบคลุมบัญชีที่ map
            # ไว้หลายที่ — เช่น sga เป็นตัวปิด opex) ไม่ใช่แค่ผลรวมรายบัญชี
            row = pair_row(key, label, pl[key], plp[key])
            row["kind"] = "line"
            row["accounts"] = accounts
            row["pct_of_revenue"] = pct_of_rev(pl[key], pl["revenue"])
            row["configured"] = bool(ids) if src[0] == "map" else True
            if src[0] == "type":
                row["types"] = list(src[1])
                row["account_ids"] = []
                row["exclude_ids"] = []
            elif src[0] == "type_ex":
                row["types"] = list(src[1])
                row["account_ids"] = []
                row["exclude_ids"] = sorted(pnl_distributed)
            else:  # map
                row["types"] = []
                row["account_ids"] = ids
                row["exclude_ids"] = []
            pnl_rows.append(row)

        # ---- Cash Flow ทางอ้อมแบบ waterfall (CFO → CFI → CFF → Net change) ----
        cf_div_ids = shared["cf_dividend_ids"]

        def _map_union(keys):
            out = set()
            for k in keys:
                out |= bs_map_ids.get(k, set())
            return out

        cf_debt_ids = _map_union(CF_DEBT_KEYS)
        cf_lease_ids = _map_union(CF_LEASE_KEYS)
        cf_invest_other_ids = _map_union(CF_INVEST_OTHER_KEYS)
        cf_fin_carveout = cf_debt_ids | cf_lease_ids

        def cf_dt(types, cur_key, open_key, exclude=None):
            """cash effect = −(Σ balance งวดนี้ − Σ balance ต้นงวด) ของ type"""
            if not exclude:
                return -(self._sum_type(shared, cur_key, types)
                         - self._sum_type(shared, open_key, types))
            total = 0.0
            for aid, atype in shared["acc_type"].items():
                if atype in types and aid not in exclude:
                    total += (shared[cur_key].get(aid, 0.0)
                              - shared[open_key].get(aid, 0.0))
            return -total

        def cf_di(ids, cur_key, open_key):
            return -sum(shared[cur_key].get(a, 0.0)
                        - shared[open_key].get(a, 0.0) for a in ids)

        def cf_val(src, cur_key, open_key, pl_total):
            kind = src[0]
            if kind == "pl":
                return pl_total[src[1]]
            if kind == "d_type":
                return cf_dt(src[1], cur_key, open_key)
            if kind == "d_type_ex":
                return cf_dt(src[1], cur_key, open_key, _map_union(src[2]))
            if kind == "d_ids":
                return cf_di(_map_union(src[1]), cur_key, open_key)
            if kind == "map":
                return cf_di(cf_div_ids, cur_key, open_key)
            if kind == "capex":
                return (cf_dt(("asset_fixed",), cur_key, open_key)
                        - pl_total["depreciation"])
            if kind == "invest_other":
                return (cf_dt(("asset_non_current",), cur_key, open_key,
                              cf_invest_other_ids)
                        + cf_di(cf_invest_other_ids, cur_key, open_key))
            if kind == "wc_other":
                return (cf_dt(CF_OTHER_CA_TYPES, cur_key, open_key,
                              shared["inv_ids"])
                        + cf_dt(CF_OTHER_CL_TYPES, cur_key, open_key,
                                cf_fin_carveout))
            if kind == "equity_fin":
                return (cf_dt(EQUITY_TYPES, cur_key, open_key, cf_div_ids)
                        + cf_dt(CF_FIN_LIAB_TYPES, cur_key, open_key,
                                cf_fin_carveout))
            return 0.0

        def cf_drill(src):
            kind = src[0]
            if kind == "pl":
                return ((list(PL_TYPES), [], []) if src[1] == "net"
                        else ([], sorted(pnl_map_ids["dep"]), []))
            if kind == "d_type":
                return list(src[1]), [], []
            if kind == "d_type_ex":
                return list(src[1]), [], sorted(_map_union(src[2]))
            if kind == "d_ids":
                return [], sorted(_map_union(src[1])), []
            if kind == "map":
                return [], sorted(cf_div_ids), []
            if kind == "capex":
                return ["asset_fixed"], [], []
            if kind == "invest_other":
                return (["asset_non_current"], sorted(cf_invest_other_ids), [])
            if kind == "wc_other":
                return (list(CF_OTHER_CA_TYPES + CF_OTHER_CL_TYPES), [],
                        sorted(shared["inv_ids"] | cf_fin_carveout))
            if kind == "equity_fin":
                return (list(EQUITY_TYPES + CF_FIN_LIAB_TYPES), [],
                        sorted(cf_div_ids | cf_fin_carveout))
            return [], [], []

        cf_rows = []
        cf_sec_sum = defaultdict(lambda: [0.0, 0.0])
        cf_sub = {}
        for kind, sec, key, label, src in CF_WATERFALL:
            if kind == "subtotal":
                if src[0] == "lines":
                    cur, prior = cf_sec_sum[src[1]]
                else:
                    cur = sum(cf_sub[k]["amount"] for k in src[1])
                    prior = sum(cf_sub[k]["prior"] for k in src[1])
                row = pair_row(key, label, cur, prior)
                row.update(kind="subtotal", sec=sec, accounts=[])
                cf_rows.append(row)
                cf_sub[key] = row
                continue
            cur = cf_val(src, "bal_cum", "bal_open", pl)
            prior = cf_val(src, "bal_cum_prior", "bal_open_prior", plp)
            types, account_ids, exclude_ids = cf_drill(src)
            row = pair_row(key, label, cur, prior)
            row.update(
                kind="line", sec=sec, accounts=[], types=types,
                account_ids=account_ids, exclude_ids=exclude_ids,
                configured=bool(account_ids) if src[0] == "map" else True)
            cf_rows.append(row)
            cf_sec_sum[sec][0] += cur
            cf_sec_sum[sec][1] += prior

        opening_cash = self._sum_type(shared, "bal_open", ("asset_cash",))
        closing_cash = self._sum_type(shared, "bal_cum", ("asset_cash",))
        net_change = cf_sub["net_change"]["amount"]
        cashflow = {
            "rows": cf_rows,
            "opening_cash": round(opening_cash, 2),
            "closing_cash": round(closing_cash, 2),
            "net_change": round(net_change, 2),
            # ส่วนต่างที่อธิบายไม่ได้ (บัญชี off_balance / เงินปันผลที่ยังไม่ map /
            # residual timing ของ P&L↔equity) — โชว์เตือนเมื่อไม่เป็นศูนย์
            "check": round(closing_cash - opening_cash - net_change, 2),
        }

        # ---- AR aging (ถังเดียวกับ AP — นับจากวันนี้) ----
        today = f["today"]
        buckets = {"current": 0.0, "b1_30": 0.0, "b31_60": 0.0,
                   "b60_plus": 0.0}
        customers = defaultdict(lambda: dict.fromkeys(
            ("current", "b1_30", "b31_60", "b60_plus", "total"), 0.0))
        customer_names = {}
        for item in shared["ar_items"]:
            due = item["date_maturity"] or item["date"]
            days = (today - due).days if due else 0
            if days <= 0:
                bucket = "current"
            elif days <= 30:
                bucket = "b1_30"
            elif days <= 60:
                bucket = "b31_60"
            else:
                bucket = "b60_plus"
            amount = item["amount_residual"]
            buckets[bucket] += amount
            partner = item["partner_id"]
            key = partner[0] if partner else 0
            customer_names[key] = partner[1] if partner else _("ไม่ระบุ")
            customers[key][bucket] += amount
            customers[key]["total"] += amount
        ar_total = sum(buckets.values())
        top_customers = [
            dict(
                {k: round(v, 2) for k, v in row.items()},
                partner_id=self._drill_partner(key),
                name=customer_names[key],
                overdue=round(
                    row["b1_30"] + row["b31_60"] + row["b60_plus"], 2),
            )
            for key, row in sorted(
                customers.items(), key=lambda kv: -kv[1]["total"])[:15]
        ]
        overdue = buckets["b1_30"] + buckets["b31_60"] + buckets["b60_plus"]
        ar_aging = {
            "buckets": {k: round(v, 2) for k, v in buckets.items()},
            "total": round(ar_total, 2),
            "overdue": round(overdue, 2),
            "overdue_pct": round(overdue / ar_total * 100.0, 1)
            if ar_total else 0.0,
            "customers": top_customers,
            "source": self._invoice_source_group(f, shared),
        }

        # summary กะทัดรัดสำหรับ AI brief (ตัดแถวรายบัญชีออก)
        ai_summary = {
            "balance_sheet": [
                {"label": r["label"], "amount": r["amount"],
                 "prior": r["prior"], "delta_pct": r["delta_pct"],
                 "kind": r["kind"], "sec": r["sec"]}
                for r in bs_rows
            ],
            "pnl": [
                {"label": r["label"], "amount": r["amount"],
                 "prior": r["prior"], "delta_pct": r["delta_pct"],
                 "kind": r["kind"]}
                for r in pnl_rows
            ],
            "cashflow": {
                r["key"]: r["amount"]
                for r in cf_rows if r["kind"] == "subtotal"
            } | {
                "opening_cash": cashflow["opening_cash"],
                "closing_cash": cashflow["closing_cash"],
            },
            "ar_aging": dict(ar_aging, customers=top_customers[:5]),
        }

        return {
            "as_of": str(f["as_of"]),
            "as_of_prior": str(f["as_of_prior"]),
            "pnl": {"rows": pnl_rows},
            "balance_sheet": {"rows": bs_rows, "check": bs_check},
            "cashflow": cashflow,
            "ar_aging": ar_aging,
            "ai_summary": ai_summary,
        }

    # ------------------------------------------------------------------
    # Risk & Scenarios (สมมติฐาน → ผลลัพธ์ → ความอ่อนไหว → ทะเบียนความเสี่ยง)
    # ------------------------------------------------------------------
    def _auto_alerts(self, f, shared):
        """ความเสี่ยงที่ระบบตรวจเองจากข้อมูลจริง — ใช้ทั้ง Overview และ Risk tab

        ทุกแถวต้องมี ``impact`` เป็น "เงิน" เสมอ (ประมาณการเท่าที่ข้อมูลบอกได้)
        ตาราง Early-Warning จัดลำดับความสำคัญจากยอดนี้ ไม่ใช่จากระดับสีอย่างเดียว

        จำผลไว้เพราะถูกเรียกสองรอบ (Overview แล้ว Risk) — ทุกอย่างที่อ่านถูก
        เตรียมเสร็จก่อน `_build_overview` แล้ว (cash_forecast, ar_items,
        margin_leakage_*) ผลสองรอบจึงเท่ากันเสมอ  ผู้เรียกต่อท้าย/เรียงลิสต์
        ที่ได้ จึงต้องคืน**สำเนา**ไม่ใช่ตัวเดียวกัน"""
        if "auto_alerts" in shared:
            return list(shared["auto_alerts"])
        alerts = []
        forecast = shared.get("cash_forecast") or {}
        if forecast.get("alerts"):
            first = forecast["alerts"][0]
            last = forecast["alerts"][-1]
            alerts.append({
                "name": _("เงินสดต่ำกว่าขั้นต่ำ %s – %s") % (
                    first["label"], last["label"]),
                "indicator": _("Projected cash < Minimum Cash"),
                "level": "high",
                "category": "cash",
                "source": "auto",
                "impact": round(max(
                    a["gap"] for a in forecast["alerts"]), 2),
            })
        today = f["today"]
        overdue60 = sum(
            item["amount_residual"] for item in shared["ar_items"]
            if (item["date_maturity"] or item["date"])
            and (today - (item["date_maturity"] or item["date"])).days > 60
        )
        ar_total = sum(i["amount_residual"] for i in shared["ar_items"])
        if ar_total and overdue60 / ar_total > 0.15:
            alerts.append({
                "name": _("ลูกหนี้ค้างเกิน 60 วันสูง"),
                "indicator": _("AR > 60 วัน = %.1f%% ของลูกหนี้ทั้งหมด")
                % (overdue60 / ar_total * 100.0),
                "level": "medium",
                "category": "ar",
                "source": "auto",
                "impact": round(overdue60, 2),
            })
        leakage_pct = shared.get("margin_leakage_pct")
        threshold = shared.get("margin_leakage_threshold")
        if (leakage_pct is not None and threshold is not None
                and leakage_pct > threshold):
            alerts.append({
                "name": _("Margin โครงการหลุดงบเกินเพดาน"),
                "indicator": _("Leakage %.1f%% > เพดาน %.1f%%")
                % (leakage_pct, threshold),
                "level": "high",
                "category": "margin",
                "source": "auto",
                "impact": round(shared.get("margin_leakage_amount") or 0.0, 2),
            })
        if f["echo"]["multi_currency"]:
            exposure = self._fx_exposure(f, shared)
            move_pct = self._scenario_assumptions(shared)["downside"][
                "fx_move_pct"]
            alerts.append({
                "name": _("กลุ่มมีหลายสกุลเงิน"),
                "indicator": _(
                    "แปลงเป็น %s ด้วยอัตราปิด ณ %s — ยอดเทียบปีก่อนใช้อัตรา "
                    "ณ %s ผลต่างอัตราจึงไม่ถูกแยกเป็นบรรทัดต่างหาก"
                ) % (f["echo"]["currency"], f["echo"]["as_of"],
                     f["echo"]["as_of_prior"]),
                "level": "medium",
                "category": "fx",
                "source": "auto",
                "impact": round(exposure * move_pct / 100.0, 2),
            })
        shared["auto_alerts"] = alerts
        return list(alerts)

    def _top_risks(self, f, shared):
        risks = self.env["biz.smart.finance.risk"].search([
            ("company_id", "in", f["cids"]), ("state", "=", "open"),
        ], limit=8)
        rows = [{
            "id": risk.id,
            "name": risk.name,
            "level": risk.level,
            "score": risk.score,
            "category": risk.category,
            "source": "register",
        } for risk in risks]
        rows += self._auto_alerts(f, shared)
        order = {"high": 0, "medium": 1, "low": 2}
        rows.sort(key=lambda r: (order.get(r["level"], 3), -r.get("score", 0)))
        return rows[:8]

    # ---------------- Risk & Scenarios: สมมติฐาน ----------------
    def _scenario_assumptions(self, shared):
        """ตัวเลขสมมติฐานของทั้งสาม scenario (เฉลี่ยจากการตั้งค่าของแต่ละบริษัท)

        สองตัวแรก (เลื่อนเงินเข้า / margin หด) คือตัวคูณที่ **engine ใช้จริง**
        ทุกแท็บ — ``collection_delay_days`` จึงต้องมาจากค่าคงที่ที่กริดเงินสด
        ใช้เลื่อนจริง (SCENARIO_SHIFT_WEEKS) ไม่ใช่ตัวเลขที่ตั้งใหม่ให้สวย
        ส่วนที่เหลือใช้เฉพาะ Key Outcome / Sensitivity ของแท็บนี้
        """
        if shared.get("risk_assumptions"):
            return shared["risk_assumptions"]
        configs = list(shared["cfg_map"].values())

        def avg(field, default):
            values = [cfg[field] for cfg in configs if cfg[field]]
            return sum(values) / len(values) if values else default

        sets = {
            "base": {
                "collection_delay_days": 0,
                "collection_share_pct": 0.0,
                "shift_months": 0,
                "margin_hit_pp": 0.0,
                "material_cost_pct": 0.0,
                "interest_bps": 0.0,
                "booking_conversion_pct": 0.0,
                "install_delay_days": 0,
                "fx_move_pct": 0.0,
            },
        }
        for scenario, fallback in (
            ("downside", (20.0, 2.0, 5.0, 100.0, 10.0, 30, 5.0)),
            ("stress", (40.0, 5.0, 10.0, 200.0, 25.0, 60, 10.0)),
        ):
            sets[scenario] = {
                "collection_delay_days": SCENARIO_SHIFT_WEEKS[scenario] * 7,
                "collection_share_pct": round(
                    avg("%s_collection_delay_pct" % scenario, fallback[0]), 1),
                "shift_months": SCENARIO_SHIFT_MONTHS[scenario],
                "margin_hit_pp": round(
                    avg("%s_margin_hit_pct" % scenario, fallback[1]), 1),
                "material_cost_pct": round(
                    avg("%s_material_cost_pct" % scenario, fallback[2]), 1),
                "interest_bps": round(
                    avg("%s_interest_rate_bps" % scenario, fallback[3])),
                "booking_conversion_pct": round(
                    avg("%s_booking_conversion_pct" % scenario, fallback[4]), 1),
                "install_delay_days": round(
                    avg("%s_install_delay_days" % scenario, fallback[5])),
                "fx_move_pct": round(
                    avg("%s_fx_move_pct" % scenario, fallback[6]), 1),
            }
        shared["risk_assumptions"] = sets
        return sets

    def _assumption_tiles(self, values):
        """การ์ดสมมติฐาน 6 ใบ — ค่าติดลบ = แย่ลง (margin/อัตราปิดงานขาย)"""
        share = values["collection_share_pct"]
        return [
            {
                "code": "collection_delay",
                "label": "Collection Delay",
                "label_th": _("เลื่อนรับชำระเงิน"),
                "icon": "fa-clock-o",
                "value": values["collection_delay_days"],
                "unit": "days",
                "digits": 0,
                "note": (
                    _("ของเงินเข้า %s%%") % self._fmt_pp(share) if share else ""),
                "engine": True,
            },
            {
                "code": "booking_conversion",
                "label": "Booking Conversion",
                "label_th": _("อัตราปิดงานขาย"),
                "icon": "fa-line-chart",
                "value": -values["booking_conversion_pct"],
                "unit": "%",
                "digits": 1,
                "note": "",
                "engine": False,
            },
            {
                "code": "gross_margin",
                "label": "Gross Margin",
                "label_th": _("อัตรากำไรขั้นต้น"),
                "icon": "fa-star-o",
                "value": -values["margin_hit_pp"],
                "unit": "pp",
                "digits": 1,
                "note": "",
                "engine": True,
            },
            {
                "code": "material_cost",
                "label": "Material Cost",
                "label_th": _("ต้นทุนวัสดุ"),
                "icon": "fa-cube",
                "value": values["material_cost_pct"],
                "unit": "%",
                "digits": 1,
                "note": "",
                "engine": False,
            },
            {
                "code": "interest_rate",
                "label": "Interest Rate",
                "label_th": _("อัตราดอกเบี้ย"),
                "icon": "fa-percent",
                "value": values["interest_bps"],
                "unit": "bps",
                "digits": 0,
                "note": "",
                "engine": False,
            },
            {
                "code": "install_delay",
                "label": "Project Installation Delay",
                "label_th": _("งานติดตั้งช้า"),
                "icon": "fa-wrench",
                "value": values["install_delay_days"],
                "unit": "days",
                "digits": 0,
                "note": "",
                "engine": False,
            },
        ]

    def _fx_exposure(self, f, shared):
        """มูลค่าที่ถือในสกุลต่างจากสกุลนำเสนอ (เงินสด + ลูกหนี้ − เจ้าหนี้)

        ยอดใน shared ถูกแปลงเป็นสกุลนำเสนอมาแล้ว — ที่นี่จึงคัดเฉพาะ "ของ
        บริษัทที่ใช้สกุลอื่น" ซึ่งเป็นก้อนที่มูลค่าเปลี่ยนตามอัตราแลกเปลี่ยน
        """
        if "fx_exposure" in shared:
            return shared["fx_exposure"]
        presentation = f["presentation_currency"]
        foreign = {
            company.id
            for company in self.env["res.company"].browse(f["cids"])
            if company.currency_id != presentation
        }
        if not foreign:
            shared["fx_exposure"] = 0.0
            return 0.0
        acc_company = shared["acc_company"]
        total = sum(
            shared["bal_cum"].get(account_id, 0.0)
            for account_id in shared["liquidity_ids"]
            if acc_company.get(account_id) in foreign
        )
        for item in shared["ar_items"]:
            if item["company_id"] and item["company_id"][0] in foreign:
                total += item["amount_residual"]
        for item in shared["ap_items"]:
            if item["company_id"] and item["company_id"][0] in foreign:
                total -= item["amount_residual"]
        shared["fx_exposure"] = abs(total)
        return shared["fx_exposure"]

    # ---------------- Risk & Scenarios: ผลลัพธ์ ----------------
    def _risk_cash_path(self, basis, values, months, debt):
        """เส้นเงินสดปลายเดือนของ scenario หนึ่ง ๆ ตามสมมติฐาน values

        ใช้ฐานรายเดือน "ก่อนปรับ scenario" ที่แท็บ Forecast เก็บไว้ให้ แล้ว
        ปรับตามลำดับเดียวกับ engine: เลื่อนเงินเข้า → หั่นงานขายที่ปิดไม่ได้ →
        เลื่อนงานติดตั้ง → บวกต้นทุนวัสดุ/margin ที่หด → บวกดอกเบี้ยที่เพิ่ม
        """
        legs = basis["legs"]
        take = lambda key: [legs[key][i] for i in range(months)]
        collections = take("collections")
        pipeline_in = take("pipeline_in")
        pipeline_cost = take("pipeline_cost")
        other_in = take("other_in")
        out_ap = take("ap_committed")
        out_boq = take("boq_budget")
        out_fixed = [
            legs["payroll_opex"][i] + legs["tax_other"][i]
            for i in range(months)
        ]
        revenue = basis["revenue"][:months]

        def shift(series, offset, share=1.0):
            """เลื่อนเงินไปข้างหน้า offset เดือน — ส่วนที่ตกเกินช่วงถือว่า
            "ยังไม่เข้าในช่วงที่มอง" (นี่คือความเสี่ยงที่ต้องเห็น ไม่ใช่บั๊ก)"""
            if not offset or not share:
                return series
            moved = [0.0] * months
            for index, amount in enumerate(series):
                stay = amount * (1.0 - share)
                moved[index] += stay
                if index + offset < months:
                    moved[index + offset] += amount - stay
            return moved

        collections = shift(
            collections, values["shift_months"],
            values["collection_share_pct"] / 100.0)
        conversion = 1.0 - values["booking_conversion_pct"] / 100.0
        pipeline_in = [amount * conversion for amount in pipeline_in]
        pipeline_cost = [amount * conversion for amount in pipeline_cost]
        install_shift = int(round(values["install_delay_days"] / 30.0))
        pipeline_in = shift(pipeline_in, install_shift, 1.0)
        pipeline_cost = shift(pipeline_cost, install_shift, 1.0)

        material = 1.0 + values["material_cost_pct"] / 100.0
        margin_hit = values["margin_hit_pp"] / 100.0
        interest_month = debt * values["interest_bps"] / 10000.0 / 12.0

        closing, running = [], basis["opening"]
        for index in range(months):
            inflow = collections[index] + pipeline_in[index] + other_in[index]
            outflow = (
                out_ap[index] + out_fixed[index]
                + (out_boq[index] + pipeline_cost[index]) * material
                + revenue[index] * margin_hit
                + interest_month
            )
            running += inflow - outflow
            closing.append(round(running, 2))
        return closing

    def _risk_runway(self, opening, closing, floor):
        """กี่เดือนกว่าเงินสดจะแตะเกณฑ์ขั้นต่ำ (None = ยังไม่แตะและไม่ได้เผาเงิน)"""
        previous = opening
        for index, value in enumerate(closing):
            if value < floor:
                drop = previous - value
                fraction = (previous - floor) / drop if drop > 0 else 0.0
                return round(index + min(max(fraction, 0.0), 1.0), 1)
            previous = value
        # ยังไม่แตะเกณฑ์ในช่วงที่มองเห็น — ต่อเส้นด้วยอัตราเผาเงิน 3 เดือนท้าย
        series = [opening] + closing
        tail = series[-4:]
        steps = len(tail) - 1
        burn = (tail[0] - tail[-1]) / steps if steps else 0.0
        if burn <= 0:
            return None
        return round(len(closing) + (closing[-1] - floor) / burn, 1)

    def _risk_sensitivity(self, f, shared, basis, values, months, capital):
        """ผลกระทบเต็มขนาดของแต่ละช็อก แยกทีละตัวแปร (ตอร์นาโด)

        คนละกติกากับเส้นเงินสดของ Key Outcome ตรงที่ **ไม่คิดสัดส่วน** ของ
        scenario (เช่นเลื่อนเงินเข้าเฉพาะ 20% ของยอด) — ที่นี่ตอบว่า "ถ้าช็อก
        นี้เกิดเต็มขนาดกับทั้งพอร์ต จะกระทบเท่าไร" หัวการ์ดบนจอเขียนกำกับไว้
        """
        days = max(months * 30.4, 1.0)
        revenue = sum(basis["revenue"][:months])
        pipeline_revenue = sum(basis["pipeline_revenue"][:months])
        project_cost = sum(basis["project_cost"][:months])
        collections = sum(
            basis["legs"]["collections"][i] + basis["legs"]["pipeline_in"][i]
            for i in range(months)
        )
        pl = shared["pl_ytd"]["total"]
        margin_rate = (pl["gross"] / pl["revenue"]) if pl["revenue"] else 0.30
        margin_rate = min(max(margin_rate, 0.0), 1.0)
        exposure = self._fx_exposure(f, shared)

        rows = [
            {
                "code": "collection_delay",
                "label": "Collection Delay",
                "label_th": _("เลื่อนรับชำระเงิน"),
                "shock": _("+%s วัน") % values["collection_delay_days"],
                "basis": "cash",
                "amount": collections / days * values["collection_delay_days"],
            },
            {
                "code": "gross_margin",
                "label": "Project Margin Leakage",
                "label_th": _("กำไรขั้นต้นหด"),
                "shock": _("-%s pp") % self._fmt_pp(values["margin_hit_pp"]),
                "basis": "ebitda",
                "amount": revenue * values["margin_hit_pp"] / 100.0,
            },
            {
                "code": "material_cost",
                "label": "Material Cost",
                "label_th": _("ต้นทุนวัสดุแพงขึ้น"),
                "shock": _("+%s%%") % self._fmt_pp(values["material_cost_pct"]),
                "basis": "ebitda",
                "amount": project_cost * values["material_cost_pct"] / 100.0,
            },
            {
                "code": "fx_exposure",
                "label": "FX Exposure",
                "label_th": _("ค่าเงินผันผวน"),
                "shock": _("+%s%%") % self._fmt_pp(values["fx_move_pct"]),
                "basis": "ebitda",
                "amount": exposure * values["fx_move_pct"] / 100.0,
            },
            {
                "code": "interest_rate",
                "label": "Interest Rate",
                "label_th": _("ดอกเบี้ยขึ้น"),
                "shock": _("+%s bps") % int(values["interest_bps"]),
                "basis": "ebitda",
                "amount": (capital["debt"] * values["interest_bps"] / 10000.0
                           * months / 12.0),
            },
            {
                "code": "install_delay",
                "label": "Installation Delay",
                "label_th": _("งานติดตั้งช้า"),
                "shock": _("+%s วัน") % values["install_delay_days"],
                "basis": "ebitda",
                "amount": min(
                    revenue / days * values["install_delay_days"], revenue,
                ) * margin_rate,
            },
            {
                "code": "booking_conversion",
                "label": "Booking Conversion",
                "label_th": _("ปิดงานขายได้น้อยลง"),
                "shock": _("-%s%%") % self._fmt_pp(
                    values["booking_conversion_pct"]),
                "basis": "ebitda",
                "amount": (pipeline_revenue
                           * values["booking_conversion_pct"] / 100.0
                           * margin_rate),
            },
        ]
        for row in rows:
            row["amount"] = round(max(row["amount"], 0.0), 2)
        rows.sort(key=lambda r: -r["amount"])
        return rows

    def _fmt_pp(self, value):
        """เลขในป้ายช็อก: ตัด .0 ทิ้งเมื่อเป็นจำนวนเต็ม (อ่านง่ายกว่า 5.0%)"""
        return ("%.1f" % value).rstrip("0").rstrip(".")

    def _risk_outcomes(self, f, shared, basis, assumptions, capital, horizons):
        """Key Outcome ของทุก scenario × ทุกช่วงเวลา

        คำนวณครบตั้งแต่ตอนโหลด เพราะผู้ใช้สลับ "เทียบกับ" และ "ช่วงเวลา" บนจอ
        บ่อยกว่าที่จะเปลี่ยน scenario จริง — สลับแล้วต้องเปลี่ยนทันทีโดยไม่ยิงใหม่
        """
        floor = basis["min_cash"]
        nde_target = capital["nde_target"]
        outcomes = {}
        for months in horizons:
            per_scenario = {}
            base_end = None
            for scenario in ("base", "downside", "stress"):
                values = assumptions[scenario]
                closing = self._risk_cash_path(
                    basis, values, months, capital["debt"])
                if scenario == "base":
                    base_end = closing[-1]
                hit = sum(
                    row["amount"] for row in self._risk_sensitivity(
                        f, shared, basis, values, months, capital)
                    if row["basis"] == "ebitda"
                )
                # หนี้สุทธิแย่ลงเท่ากับเงินสดที่หายไปเทียบ base, ส่วนของผู้ถือหุ้น
                # ลดลงเท่ากำไรที่หายไป — สองขานี้บีบ covenant พร้อมกัน
                equity = capital["equity"] - hit
                net_debt = capital["net_debt"] + (base_end - closing[-1])
                headroom = (
                    nde_target * equity - net_debt
                    if nde_target is not None else None
                )
                low_index = min(range(months), key=lambda index: closing[index])
                per_scenario[scenario] = {
                    "runway_months": self._risk_runway(
                        basis["opening"], closing, floor),
                    "min_cash": round(min(closing), 2),
                    "min_cash_month": basis["months"][low_index]["label"],
                    "closing_end": round(closing[-1], 2),
                    "ebitda_hit": round(hit, 2),
                    "headroom": (
                        round(headroom, 2) if headroom is not None else None),
                    "nde_ratio": (
                        round(net_debt / equity, 2) if equity else None),
                }
            outcomes[str(months)] = per_scenario
        return outcomes

    # ---------------- Risk & Scenarios: ทะเบียนความเสี่ยง ----------------
    def _risk_matrix(self, f, risks):
        """แมทริกซ์ความเสี่ยง: แถว = โครงการ, คอลัมน์ = BU (บริษัท)

        ทั้งจอนี้ถือ "BU = บริษัท" เหมือนตาราง BU ของ Overview — แต่ถ้าขอบเขต
        ที่เลือกมีบริษัทเดียว คอลัมน์จะเหลือช่องเดียวทั้งตารางจนอ่านอะไรไม่ได้
        จึงสลับไปใช้ "หมวดความเสี่ยง" เป็นแกนคอลัมน์แทน (หัวตารางบอกผู้ใช้ว่า
        กำลังอ่านแกนไหนอยู่ ไม่ใช่เดาเอง)
        """
        by_company = len(f["cids"]) > 1
        if by_company:
            columns = [
                {"key": str(company.id), "label": company.name}
                for company in self.env["res.company"].browse(f["cids"])
            ]
            column_of = lambda risk: str(risk.company_id.id)
        else:
            labels = dict(
                self.env["biz.smart.finance.risk"]._fields["category"].selection)
            columns = [
                {"key": code, "label": label} for code, label in labels.items()
            ]
            column_of = lambda risk: risk.category

        cells = defaultdict(lambda: {"score": 0, "count": 0})
        row_meta = {}
        for risk in risks:
            project = risk.project_id
            row_key = str(project.id) if project else "0"
            row_meta.setdefault(row_key, {
                "key": row_key,
                "project_id": project.id if project else 0,
                "label": project.name if project else _("ไม่ผูกโครงการ"),
                "top": 0,
            })
            cell = cells[(row_key, column_of(risk))]
            cell["score"] = max(cell["score"], risk.score)
            cell["count"] += 1
            row_meta[row_key]["top"] = max(
                row_meta[row_key]["top"], risk.score)

        rows = []
        for meta in sorted(row_meta.values(), key=lambda r: -r["top"])[:12]:
            rows.append(dict(meta, cells=[
                {
                    "key": "%s:%s" % (meta["key"], column["key"]),
                    "column": column["key"],
                    "score": cells[(meta["key"], column["key"])]["score"],
                    "count": cells[(meta["key"], column["key"])]["count"],
                }
                for column in columns
            ]))
        return {
            "axis": "company" if by_company else "category",
            "axis_label": _("BU / หน่วยธุรกิจ") if by_company else _("หมวดความเสี่ยง"),
            "columns": columns,
            "rows": rows,
        }

    def _risk_early_warning(self, f, shared, risks):
        """ตารางสัญญาณเตือน — ทะเบียน + ที่ระบบตรวจเอง เรียงตามผลกระทบเป็นเงิน"""
        status_labels = dict(
            self.env["biz.smart.finance.risk"]._fields["action_status"].selection)
        rows = []
        for risk in risks:
            rows.append({
                "id": risk.id,
                "name": risk.name,
                "indicator": risk.early_warning or "",
                "level": risk.level,
                "impact": round(self._conv(
                    shared, risk.financial_impact, risk.company_id.id), 2),
                "owner": risk.action_owner_id.name or "",
                "target_date": str(risk.target_date) if risk.target_date else "",
                "status": risk.action_status,
                "status_label": status_labels.get(risk.action_status, ""),
                "source": "register",
            })
        for alert in self._auto_alerts(f, shared):
            rows.append({
                "id": False,
                "name": alert["name"],
                "indicator": alert["indicator"],
                "level": alert["level"],
                "impact": alert.get("impact") or 0.0,
                "owner": "",
                "target_date": "",
                # ตรวจเจอเองแปลว่ายังไม่มีใครรับไปทำ — ไม่ใช่ "ยังไม่เริ่ม"
                # ของแผนที่มีคนถืออยู่แล้ว จึงเป็นสถานะของตัวเอง
                "status": "no_plan",
                "status_label": _("ยังไม่มีแผนรับมือ"),
                "source": "auto",
            })
        order = {"high": 0, "medium": 1, "low": 2}
        rows.sort(key=lambda r: (-r["impact"], order.get(r["level"], 3)))
        rows = rows[:12]
        for index, row in enumerate(rows):
            row["priority"] = index + 1
        return rows

    def _build_risk(self, f, shared):
        risks = self.env["biz.smart.finance.risk"].search([
            ("company_id", "in", f["cids"]), ("state", "!=", "closed"),
        ])
        by_project = sorted(
            [{
                "id": risk.id,
                "project_id": risk.project_id.id,
                "project": risk.project_id.name,
                "name": risk.name,
                "impact": risk.impact,
                "likelihood": risk.likelihood,
                "score": risk.score,
                "level": risk.level,
                "trend": risk.trend,
            } for risk in risks if risk.project_id],
            key=lambda r: -r["score"],
        )[:12]

        assumptions = self._scenario_assumptions(shared)
        capital = self._capital_structure(shared)
        basis = shared.get("fc_basis")
        scenario = f["scenario"]
        # ตอร์นาโดต้องมีขนาดช็อกเสมอ — โหมด Base ไม่มีสมมติฐานของตัวเอง
        # จึงใช้ชุด Downside เป็น "ช็อกมาตรฐาน" (หัวการ์ดเขียนกำกับไว้)
        shock = scenario if scenario != "base" else "downside"
        # ช่วงที่เลือกดูได้จริง = ตัดตามความยาวกริดพยากรณ์ (ตั้งค่าได้ 6–18
        # เดือน) แล้วยุบตัวซ้ำ ไม่งั้น "12 เดือน" กับ "6 เดือน" ให้ตัวเลข
        # เดียวกันทั้งที่ป้ายบอกคนละช่วง
        available = len(basis["months"]) if basis else 0
        horizons = sorted({
            min(horizon, available) for horizon in RISK_HORIZONS
        } - {0})
        sensitivity = {
            str(months): self._risk_sensitivity(
                f, shared, basis, assumptions[shock], months, capital)
            for months in horizons
        }
        outcomes = self._risk_outcomes(
            f, shared, basis, assumptions, capital, horizons) if basis else {}

        return {
            "scenario": scenario,
            "multipliers": shared["scenario_fx"],
            "assumptions": {
                key: self._assumption_tiles(values)
                for key, values in assumptions.items()
            },
            "shock_scenario": shock,
            "horizons": horizons,
            "outcomes": outcomes,
            "sensitivity": sensitivity,
            "min_cash": round(basis["min_cash"], 2) if basis else 0.0,
            "nde_target": capital["nde_target"],
            "matrix": self._risk_matrix(f, risks),
            "by_project": by_project,
            "early_warning": self._risk_early_warning(f, shared, risks),
            "register_count": len(risks),
        }

    # ------------------------------------------------------------------
    # empty-state hints — บอกผู้ใช้ว่าข้อมูลที่ขาดต้องไปกรอกที่ไหน
    # ------------------------------------------------------------------
    def _empty_hints(self, f, shared):
        hints = []
        missing_cfg = [
            cid for cid in f["cids"] if cid not in shared["cfg_map"]
        ]
        if missing_cfg:
            names = ", ".join(
                self.env["res.company"].browse(missing_cfg).mapped("name"))
            hints.append({
                "code": "no_config",
                "message": _(
                    "ยังไม่ได้ตั้งค่า Smart Finance ของ %s — เงินสดขั้นต่ำ/"
                    "EBITDA/Net Debt จะยังคำนวณไม่ครบ") % names,
                "model": "biz.smart.finance.config",
            })
        elif not shared["ebitda_configured"]:
            hints.append({
                "code": "no_ebitda_map",
                "message": _(
                    "ยังไม่ได้ map บัญชีดอกเบี้ย/ภาษี — EBITDA ตอนนี้ = "
                    "กำไรสุทธิ + ค่าเสื่อมเท่านั้น"),
                "model": "biz.smart.finance.config",
            })
        if shared["has_ext_gl"]:
            ext_gl_cids = [
                cid for cid in f["cids"]
                if shared["default_gl_source"].get(cid) == "external"
            ]
            if ext_gl_cids and not self.env[
                "biz.smart.finance.ext.gl"
            ].search_count([
                ("company_id", "in", ext_gl_cids),
                ("state", "=", "posted"),
                ("date_to", "<=", str(f["as_of"])),
            ]):
                hints.append({
                    "code": "no_ext_gl",
                    "message": _(
                        "บริษัทที่ตั้งแหล่งบัญชีแยกประเภทเป็นระบบภายนอกยังไม่มี "
                        "Trial Balance ที่ยืนยันแล้วถึงงวดนี้ — งบดุล/งบกำไร"
                        "ขาดทุน/งบกระแสเงินสดของบริษัทนั้นจะว่างหรือไม่ครบ"),
                    "model": "biz.smart.finance.ext.gl",
                })
        if not self.env["biz.smart.finance.forecast.line"].search_count(
            [("company_id", "in", f["cids"])]
        ):
            hints.append({
                "code": "no_forecast_lines",
                "message": _(
                    "ยังไม่มีรายการเงินเดือน/ค่าใช้จ่ายประจำ — Cash Forecast "
                    "ยังไม่รวมรายจ่ายเหล่านี้"),
                "model": "biz.smart.finance.forecast.line",
            })
        if not shared["bank_rows"]:
            hints.append({
                "code": "no_bank_master",
                "message": _(
                    "ยังไม่มีทะเบียนธนาคาร — แท็บ Cash & Liquidity แสดงได้"
                    "เฉพาะยอดรวมทั้งกลุ่ม ยังแยกรายธนาคารไม่ได้"),
                "model": "biz.smart.finance.bank",
            })
        if not self.env["biz.smart.finance.risk"].search_count(
            [("company_id", "in", f["cids"]), ("state", "=", "open")]
        ):
            hints.append({
                "code": "no_risks",
                "message": _(
                    "Risk Register ยังว่าง — Risk Radar แสดงเฉพาะความเสี่ยง"
                    "ที่ระบบตรวจอัตโนมัติ"),
                "model": "biz.smart.finance.risk",
            })
        # แหล่งข้อมูล Inventory / Ratios
        svl_ok = "stock.valuation.layer" in self.env
        odoo_inv_cids = [
            cid for cid in f["cids"]
            if self._inv_source(shared, cid) == "odoo"
        ]
        ext_cids = [
            cid for cid in f["cids"]
            if self._inv_source(shared, cid) == "external"
            or self._ratio_source(shared, cid) == "external"
        ]
        if odoo_inv_cids and not svl_ok:
            hints.append({
                "code": "no_stock",
                "message": _(
                    "ไม่มีโมดูล Stock ในระบบ — แท็บ Inventory แสดงได้เฉพาะ"
                    "ยอด GL จากบัญชีสต๊อกที่ map ไว้ (ไม่มีหมวด/รายสินค้า)"),
                "model": "biz.smart.finance.config",
            })
        if any(
            cid in shared["cfg_map"]
            and not shared["cfg_map"][cid].inventory_account_ids
            for cid in odoo_inv_cids
        ) or any(cid not in shared["cfg_map"] for cid in odoo_inv_cids):
            hints.append({
                "code": "no_inventory_accounts",
                "message": _(
                    "ยังไม่ได้ map บัญชีสินค้าคงเหลือ — Quick Ratio จะเท่ากับ "
                    "Current Ratio และไม่มี badge กระทบยอด SVL ↔ GL"),
                "model": "biz.smart.finance.config",
            })
        if ext_cids:
            Fact = self.env["biz.smart.finance.ext.fact"]
            has_now = Fact.search_count([
                ("company_id", "in", ext_cids),
                ("date", "<=", str(f["as_of"])),
            ])
            if not has_now:
                hints.append({
                    "code": "no_ext_facts",
                    "message": _(
                        "บริษัทที่ตั้งแหล่งข้อมูลเป็นระบบภายนอกยังไม่มีตัวเลข"
                        "ถึงงวดนี้ — กรอกมือ / นำเข้าไฟล์ / กด Sync ก่อน"),
                    "model": "biz.smart.finance.ext.fact",
                })
            elif not Fact.search_count([
                ("company_id", "in", ext_cids),
                ("date", "<=", str(f["as_of_prior"])),
            ]):
                hints.append({
                    "code": "no_ext_prior",
                    "message": _(
                        "ยังไม่มีตัวเลขระบบภายนอกของงวดปีก่อน — คอลัมน์"
                        "เปรียบเทียบ YoY ของ Inventory/Ratios จะว่าง"),
                    "model": "biz.smart.finance.ext.fact",
                })
        # แหล่งข้อมูลใบแจ้งหนี้ (AR/AP) และงบศูนย์ต้นทุน
        inv_ext_cids = shared.get("inv_ext_cids") or []
        if inv_ext_cids and not self.env[
            "biz.smart.finance.ext.invoice"
        ].search_count([
            ("company_id", "in", inv_ext_cids),
            ("date", "<=", str(f["as_of"])),
        ]):
            hints.append({
                "code": "no_ext_invoices",
                "message": _(
                    "บริษัทที่ตั้งแหล่งใบแจ้งหนี้เป็นระบบภายนอกยังไม่มีเอกสาร"
                    "ถึงงวดนี้ — AR aging, AP & Payment Plan และ Cash "
                    "Forecast จะไม่มียอดค้างของบริษัทนั้น"),
                "model": "biz.smart.finance.ext.invoice",
            })
        budget_ext_cids = [
            cid for cid in f["cids"]
            if self._budget_source(shared, cid) == "external"
        ]
        if budget_ext_cids and not self.env[
            "biz.smart.finance.ext.budget"
        ].search_count([("company_id", "in", budget_ext_cids)]):
            hints.append({
                "code": "no_ext_budget",
                "message": _(
                    "บริษัทที่ตั้งแหล่งงบเป็นระบบภายนอกยังไม่มีงบศูนย์ต้นทุน — "
                    "คอลัมน์ Budget/Available ในแท็บ Controlling จะเป็นศูนย์"),
                "model": "biz.smart.finance.ext.budget",
            })
        # AI key: โชว์เฉพาะ manager (viewer เปิด Settings ไม่ได้อยู่แล้ว)
        # model=False → frontend เปิด General Settings แทน openList
        if (
            not self.env["biz.smart.finance.ai"].is_configured()
            and self.env.user.has_group("biz_smart_finance.group_bsf_manager")
        ):
            hints.append({
                "code": "no_ai_key",
                "message": _(
                    "ยังไม่ได้ตั้งค่า OpenRouter API Key — ฟีเจอร์ AI "
                    "(Brief / Copilot / รายงาน) ยังใช้ไม่ได้"),
                "model": False,
            })
        return hints

    # ------------------------------------------------------------------
    # Monthly Close Cockpit — บริษัท × งวดของปีงบที่กำลังดู
    # ------------------------------------------------------------------
    def _build_close(self, f, shared):
        """ตารางเดียวให้เห็นสถานะปิดงวด + แหล่งข้อมูลของแต่ละแท็บ (ตามค่า
        ตั้งต้นบริษัทหรือ override รายเดือน) + ผลต่าง TB ต่อบริษัทต่อเดือน
        ของปีงบที่กำลังดู — ไม่พึ่งตัวแปรภายใน _build_shared เลย ยิงคิวรีของ
        ตัวเองเพราะเรียกครั้งเดียวและต้องเห็นทุกงวดของปีงบ ไม่ใช่แค่ที่ balances()
        แตะถึง"""
        cids = f["cids"]
        cfg_map = shared["cfg_map"]
        periods = self._fy_periods(f["fy_start"], f["fy_end"])
        period_rows = self.env["biz.smart.finance.period"].search_read(
            [("company_id", "in", cids),
             ("date_from", ">=", str(f["fy_start"])),
             ("date_from", "<=", str(f["fy_end"]))],
            ["company_id", "date_from", "state", "gl_source",
             "invoice_source", "inventory_source", "ratio_source",
             "budget_source", "gl_id", "tb_diff"],
        ) if cids else []
        # search_read คืน "id" มาด้วยเสมอแม้ไม่ได้ขอ — ใช้เปิดฟอร์มจากฝั่งจอ
        rows_by_key = {
            (row["company_id"][0], row["date_from"]): row
            for row in period_rows
        }
        source_fields = (
            "gl_source", "invoice_source", "inventory_source",
            "ratio_source", "budget_source",
        )
        companies = self.env["res.company"].browse(cids)
        rows = []
        for company in companies:
            for p in periods:
                rec = rows_by_key.get((company.id, p["date_from"]))
                resolved = {
                    field: (rec[field] if rec else "") or self._cfg_source(
                        cfg_map, company.id, field)
                    for field in source_fields
                }
                rows.append(dict(resolved, **{
                    "period_id": rec["id"] if rec else False,
                    "company_id": company.id,
                    "company_name": company.name,
                    "label": p["label"],
                    "date_from": str(p["date_from"]),
                    "date_to": str(p["date_to"]),
                    "state": rec["state"] if rec else "open",
                    "gl_posted": bool(rec and rec["gl_id"]),
                    "tb_diff": round(rec["tb_diff"], 2) if rec else 0.0,
                    "has_period": bool(rec),
                }))
        return {
            "fy_label": f["echo"]["fy_label"],
            "companies": [{"id": c.id, "name": c.name} for c in companies],
            "rows": rows,
        }
