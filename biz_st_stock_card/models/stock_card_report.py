# -*- coding: utf-8 -*-
"""เครื่องยนต์คำนวณสต๊อกการ์ด — แหล่งความจริงเดียวของทั้งหน้าจอ, PDF และ Excel

หน้าจอ OWL / QWeb PDF / xlsxwriter ต้องเรียก ``get_report_data()`` ตัวนี้เท่านั้น
ห้ามมีเส้นทางคำนวณเส้นที่สอง ไม่งั้นตัวเลขบนจอกับตัวเลขในไฟล์ที่ส่งผู้ตรวจสอบ
จะเพี้ยนจากกันโดยไม่มีใครรู้

สถาปัตยกรรมโดยย่อ
------------------

1. ``_read_group`` บน ``stock.move.line`` ให้ผลรวมจำนวนต่อ
   (บริษัท, สินค้า, ที่มา, ที่ไป[, ล็อต])
2. ``_emit_facts`` แปลงแต่ละก้อนเป็น "fact" 0-2 ตัว — การโอนข้ามคลังถูกแตกเป็น
   OUT ของคลังต้นทาง + IN ของคลังปลายทาง **ตั้งแต่ตรงนี้** (core ทำแบบเดียวกันใน
   ``stock/report/report_stock_quantity.py``)
3. ``_build_tree`` เอา fact ไป pivot ตามลำดับระดับที่ผู้ใช้เลือก — การสลับแกน
   คลัง↔สินค้า จึงเป็นแค่การสลับลำดับ key ไม่ใช่โค้ดคนละเส้น
"""

import logging
import re
from datetime import date, datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_is_zero, float_round

_logger = logging.getLogger(__name__)

# ยอดยกมา / รับ / จ่าย / คงเหลือ — คู่ขนานกับ opening/period/closing ของงบทดลอง
QTY_KEYS = ("opening_qty", "in_qty", "out_qty", "closing_qty")
# จำนวนเฉพาะส่วนที่ "ข้ามขอบเขตมูลค่าของบริษัท" ใช้เป็นตัวถ่วงน้ำหนักตอนกระจายมูลค่า SVL
EXT_QTY_KEYS = ("in_qty_ext", "out_qty_ext")
VAL_KEYS = (
    "opening_value", "in_value", "out_value", "adj_value", "closing_value",
)
# ส่วนของ in_value/out_value ที่มี SVL หนุนหลังจริง (ที่เหลือคือค่าประมาณของการโอนภายใน)
EXT_VAL_KEYS = ("in_value_ext", "out_value_ext")

MEASURE_KEYS = QTY_KEYS + EXT_QTY_KEYS + VAL_KEYS + EXT_VAL_KEYS

LEVEL_LABEL = {
    "company": "บริษัท",
    "wh": "คลังสินค้า",
    "categ": "หมวดสินค้า",
    "product": "สินค้า",
    "loc": "ที่เก็บ",
    "lot": "ล็อต/ซีเรียล",
}
LEVEL_PREFIX = {
    "company": "co",
    "wh": "wh",
    "categ": "categ",
    "product": "prod",
    "loc": "loc",
    "lot": "lot",
}
LEVEL_MODEL = {
    "company": "res.company",
    "wh": "stock.warehouse",
    "categ": "product.category",
    "product": "product.product",
    "loc": "stock.location",
    "lot": "stock.lot",
}

# ตำแหน่งคงที่ในคีย์ของ fact — (company, warehouse, product, location, lot)
# location/lot เป็น 0 เมื่อผู้ใช้ไม่ได้เปิดระดับนั้น ทำให้ "ย้ายของภายในโหนดเดียวกัน"
# กลายเป็น key ต้นทาง == key ปลายทาง แล้วถูกตัดทิ้งโดยอัตโนมัติ
K_COMPANY, K_WH, K_PRODUCT, K_LOC, K_LOT = range(5)

_LINE_ID_RE = re.compile(r"^[a-z]+-\d+(?:/[a-z]+-\d+)*$")


def _zero_measures():
    return dict.fromkeys(MEASURE_KEYS, 0.0)


class StockCardReport(models.AbstractModel):
    _name = "biz.stock.card.report"
    _description = "Stock Card Engine (สต๊อกการ์ด)"

    # ==================================================================
    # Public API
    # ==================================================================
    @api.model
    def get_report_data(self, options=None):
        """คืนข้อมูลสต๊อกการ์ดทั้งชุดสำหรับ options ที่ให้มา

        :return: dict {options, company, companies, allowed_companies, warehouses,
                       picking_types, levels, lines, totals, checks, labels}
        """
        if not self.env.user.has_group("stock.group_stock_user"):
            raise AccessError(_("คุณไม่มีสิทธิ์ดูรายงานคลังสินค้า"))

        opt = self._normalize_options(options)
        companies = self.env["res.company"].browse(opt["company_ids"])
        company = self.env["res.company"].browse(opt["company_id"])
        currency = company.currency_id

        maps = self._load_maps(opt)
        stats = {
            "interwarehouse_lines": 0, "interwarehouse_qty": 0.0,
            "internal_lines": 0, "truncated_leaves": 0, "detail_rows": 0,
        }
        nodes, denominators = self._ledger_nodes(opt, maps, stats)
        svl = self._read_svl_buckets(opt) if opt["show_value"] else {}
        if opt["show_value"]:
            self._allocate_value(nodes, denominators, svl, opt, stats)
            # การกระจายมูลค่าอาจสร้างโหนดของสินค้าที่ไม่มีความเคลื่อนไหวเลยในงวด
            self._fill_product_map(opt, maps, sorted({k[K_PRODUCT] for k in nodes}))

        lines, totals = self._build_tree(nodes, opt, maps)
        if opt["detail_mode"] != "none":
            lines = self._attach_details(lines, opt, maps, stats)
        self._strip_internal(lines)

        checks = self._build_checks(lines, totals, svl, opt, currency, companies, stats)
        return {
            "options": opt,
            "company": {
                "id": company.id,
                "name": company.name,
                # ชื่อที่ขึ้นหัวรายงาน — งบรวมหลายบริษัทต้องเห็นครบทุกชื่อ
                "names": " + ".join(companies.mapped("name")),
                "count": len(companies),
                "currency_id": currency.id,
                "currency_symbol": currency.symbol,
                "decimal_places": currency.decimal_places,
                "qty_precision": opt["qty_precision"],
            },
            "companies": [{"id": c.id, "name": c.name} for c in companies],
            # ให้แถบตัวกรองใช้โดยตรง หน้าจอจะได้ไม่ต้องยิง search_read เพิ่มอีก
            "allowed_companies": [
                {"id": c.id, "name": c.name} for c in self.env.user.company_ids
            ],
            "warehouses": maps["warehouse_list"],
            "picking_types": maps["picking_type_list"],
            "levels": [
                {"type": lv, "label": LEVEL_LABEL[lv]} for lv in opt["levels"]
            ],
            "lines": lines,
            "totals": totals,
            "checks": checks,
            "labels": self._build_labels(opt, maps),
        }

    @api.model
    def action_drill_down(self, line_id, options=None, target="moves"):
        """Drill-down จากแถวรายงานไปยังข้อมูลดิบที่ประกอบเป็นยอดนั้น

        domain ถูก **สร้างใหม่จาก _base_domain()** เสมอ ไม่เคยเชื่อสิ่งที่ client
        ส่งมา — แถวที่กดกับรายการที่เห็นจึงเป็นชุดเดียวกันแน่นอน
        """
        opt = self._normalize_options(options)
        parts = self._parse_line_id(line_id)
        maps = self._load_maps(opt)

        if parts.get("mvl"):
            return self._drill_document(parts["mvl"])

        if target == "valuation":
            return self._drill_valuation(parts, opt)
        return self._drill_moves(parts, opt, maps)

    @api.model
    def format_report_date(self, value, date_format="be"):
        """dd/mm/yyyy โดยปีเป็น พ.ศ. (be) หรือ ค.ศ. (ce)"""
        if not value:
            return ""
        date = self._to_date(value)
        year = date.year + 543 if date_format == "be" else date.year
        return "%02d/%02d/%d" % (date.day, date.month, year)

    @api.model
    def format_report_datetime(self, value, tz=None, date_format="be"):
        """แปลง datetime naive-UTC เป็น dd/mm/yyyy HH:MM ตามเขตเวลาที่ให้มา"""
        if not value:
            return ""
        if isinstance(value, str):
            value = fields.Datetime.to_datetime(value)
        zone = pytz.timezone(tz or "UTC")
        local = pytz.UTC.localize(value).astimezone(zone)
        year = local.year + 543 if date_format == "be" else local.year
        return "%02d/%02d/%d %02d:%02d" % (
            local.day, local.month, year, local.hour, local.minute,
        )

    # ==================================================================
    # Options
    # ==================================================================
    @api.model
    def _normalize_options(self, options):
        """clamp / whitelist ทุกคีย์ที่ข้ามเขตแดน RPC มา แล้วส่งกลับให้ client ใช้แทนของเดิม"""
        opt = dict(options or {})
        company_ids = self._resolve_company_ids(opt)
        main_id = self.env.company.id if self.env.company.id in company_ids else company_ids[0]
        company = self.env["res.company"].browse(main_id)

        today = fields.Date.context_today(self)
        date_from = self._to_date(opt.get("date_from")) or today.replace(day=1)
        date_to = self._to_date(opt.get("date_to")) or today
        if date_to < date_from:
            date_from, date_to = date_to, date_from

        tz = opt.get("tz") or self.env.user.tz or "UTC"
        try:
            pytz.timezone(tz)
        except pytz.UnknownTimeZoneError:
            tz = "UTC"
        dt_from, dt_to = self._period_bounds(date_from, date_to, tz)

        show_value = bool(opt.get("show_value", True)) and self._can_see_value()
        normalized = {
            "company_id": company.id,
            "company_ids": company_ids,
            "company_mode": opt.get("company_mode") or "consolidated",
            "date_from": fields.Date.to_string(date_from),
            "date_to": fields.Date.to_string(date_to),
            "tz": tz,
            "datetime_from": fields.Datetime.to_string(dt_from),
            "datetime_to": fields.Datetime.to_string(dt_to),
            "date_format": opt.get("date_format") or "be",
            "group_mode": opt.get("group_mode") or "wh_product",
            "group_categ": bool(opt.get("group_categ", False)),
            "group_location": bool(opt.get("group_location", False)),
            "group_lot": bool(opt.get("group_lot", False)),
            # 0 เป็นค่าที่มีความหมาย (ยุบหมด) ห้ามใช้ ``or`` เป็นค่าตั้งต้น
            "unfold_level": self._int_or(opt.get("unfold_level"), 1),
            "unfolded": self._clean_unfolded(opt.get("unfolded")),
            "detail_mode": opt.get("detail_mode") or "unfolded",
            "detail_limit": int(opt.get("detail_limit") or 200),
            "detail_total_limit": int(opt.get("detail_total_limit") or 5000),
            "max_detail_leaves": int(opt.get("max_detail_leaves") or 200),
            "warehouse_ids": self._clean_ids(opt.get("warehouse_ids")),
            "location_ids": self._clean_ids(opt.get("location_ids")),
            "product_ids": self._clean_ids(opt.get("product_ids")),
            "categ_ids": self._clean_ids(opt.get("categ_ids")),
            "lot_ids": self._clean_ids(opt.get("lot_ids")),
            "picking_type_ids": self._clean_ids(opt.get("picking_type_ids")),
            "include_inventory": bool(opt.get("include_inventory", True)),
            "include_scrap": bool(opt.get("include_scrap", True)),
            "include_consignment": bool(opt.get("include_consignment", False)),
            "show_value": show_value,
            "value_mode": opt.get("value_mode") or "imputed",
            "value_date_basis": opt.get("value_date_basis") or "move",
            "opening_basis": opt.get("opening_basis") or "moves",
            "display_product": opt.get("display_product") or "movement",
            "max_groups": int(opt.get("max_groups") or 20000),
            "debug_timing": bool(opt.get("debug_timing", False)),
        }
        if normalized["company_mode"] not in ("consolidated", "split"):
            normalized["company_mode"] = "consolidated"
        if normalized["date_format"] not in ("be", "ce"):
            normalized["date_format"] = "be"
        if normalized["group_mode"] not in ("wh_product", "product_wh"):
            normalized["group_mode"] = "wh_product"
        if normalized["detail_mode"] not in ("none", "unfolded", "all"):
            normalized["detail_mode"] = "unfolded"
        if normalized["value_mode"] not in ("imputed", "svl"):
            normalized["value_mode"] = "imputed"
        if normalized["value_date_basis"] not in ("move", "svl_create"):
            normalized["value_date_basis"] = "move"
        if normalized["opening_basis"] not in ("moves", "none"):
            normalized["opening_basis"] = "moves"
        if normalized["display_product"] not in ("movement", "not_zero", "all"):
            normalized["display_product"] = "movement"

        normalized["unfold_level"] = max(0, min(7, normalized["unfold_level"]))
        normalized["detail_limit"] = max(1, min(2000, normalized["detail_limit"]))
        normalized["detail_total_limit"] = max(1, min(50000, normalized["detail_total_limit"]))
        normalized["max_detail_leaves"] = max(1, min(2000, normalized["max_detail_leaves"]))
        normalized["max_groups"] = max(1000, min(200000, normalized["max_groups"]))

        # "แสดงทุกรายการเคลื่อนไหว" โดยไม่จำกัดสินค้าเลย = คิวรีระเบิด จึงลดระดับให้
        # อัตโนมัติแทนที่จะปล่อยให้ผู้ใช้รอแล้ว timeout
        normalized["detail_downgraded"] = False
        if normalized["detail_mode"] == "all" and not (
            normalized["product_ids"] or normalized["categ_ids"] or normalized["lot_ids"]
        ):
            normalized["detail_mode"] = "unfolded"
            normalized["detail_downgraded"] = True

        normalized["value_hidden_reason"] = (
            "no_accounting_group"
            if opt.get("show_value", True) and not show_value
            else False
        )
        normalized["levels"] = self._group_levels(normalized)
        normalized["qty_precision"] = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        return normalized

    @api.model
    def _resolve_company_ids(self, opt):
        """บริษัทที่รายงานจะครอบคลุม — ค่าตั้งต้นคือชุดที่เลือกอยู่ใน company switcher

        ตรวจสิทธิ์กับ ``user.company_ids`` (บริษัททั้งหมดที่ผู้ใช้เข้าถึงได้) ไม่ใช่
        ``env.companies`` (ชุดที่ติ๊กอยู่ตอนนี้) — wizard ที่บันทึกตัวกรองไว้ก่อนแล้ว
        ผู้ใช้สลับ switcher จึงยังสั่งพิมพ์ได้ โดยที่บริษัทนอกสิทธิ์ยังถูกปฏิเสธเสมอ
        """
        requested = opt.get("company_ids")
        if not requested:
            single = opt.get("company_id")
            requested = [single] if single else self.env.companies.ids
        requested = [int(c) for c in requested if c]
        if not requested:
            requested = self.env.companies.ids

        allowed = set(self.env.user.company_ids.ids)
        denied = [c for c in requested if c not in allowed]
        if denied:
            names = self.env["res.company"].sudo().browse(denied).mapped("name")
            raise AccessError(
                _("คุณไม่มีสิทธิ์ดูข้อมูลของบริษัท: %s") % ", ".join(names)
            )
        seen = {}
        for company_id in requested:
            seen.setdefault(company_id, True)
        return list(seen)

    @api.model
    def _period_bounds(self, date_from, date_to, tz):
        """ขอบงวดเป็นเวลาท้องถิ่นของผู้ใช้ แปลงเป็น naive UTC ครั้งเดียวที่นี่

        ``stock.move.line.date`` เก็บเป็น UTC ถ้าเทียบกับวันที่ตรง ๆ ของที่รับเข้า
        ตอน 23:30 เวลาไทยของวันสุดท้ายจะหลุดงวดไปอยู่เดือนถัดไป
        """
        zone = pytz.timezone(tz)
        start = zone.localize(datetime.combine(date_from, time.min))
        end = zone.localize(datetime.combine(date_to, time(23, 59, 59)))
        return (
            start.astimezone(pytz.UTC).replace(tzinfo=None),
            end.astimezone(pytz.UTC).replace(tzinfo=None),
        )

    @api.model
    def _group_levels(self, opt):
        """ลำดับระดับของต้นไม้รายงาน — ``group_mode`` เป็นแค่การสลับลำดับ ไม่ใช่โค้ดคนละเส้น"""
        levels = []
        if opt["company_mode"] == "split" and len(opt["company_ids"]) > 1:
            levels.append("company")
        if opt["group_mode"] == "wh_product":
            levels.append("wh")
            if opt["group_categ"]:
                levels.append("categ")
            levels.append("product")
        else:
            if opt["group_categ"]:
                levels.append("categ")
            levels.append("product")
            levels.append("wh")
        if opt["group_location"]:
            levels.append("loc")
        if opt["group_lot"]:
            levels.append("lot")
        return levels

    @api.model
    def _can_see_value(self):
        """ใครเห็นคอลัมน์มูลค่าได้บ้าง

        ผู้ใช้ที่มีสิทธิ์บัญชีคือกลุ่มเป้าหมายหลัก (ต้นทุนสินค้าคงเหลือเป็นตัวเลขงบการเงิน)
        และ stock manager ก็เห็นได้เพราะ ACL ของ stock.valuation.layer ให้สิทธิ์ไว้อยู่แล้ว
        นโยบายที่เข้มกว่านี้ override เมธอดเดียวตัวนี้พอ
        """
        return (
            self.env.user.has_group("account.group_account_readonly")
            or self.env.user.has_group("stock.group_stock_manager")
        )

    @api.model
    def _int_or(self, value, default):
        if value is None or value is False or value == "":
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @api.model
    def _to_date(self, value):
        if not value:
            return False
        if isinstance(value, str):
            return fields.Date.to_date(value)
        return value

    @api.model
    def _clean_ids(self, value):
        out = []
        for item in value or []:
            try:
                item = int(item)
            except (TypeError, ValueError):
                continue
            if item and item not in out:
                out.append(item)
        return out

    @api.model
    def _clean_unfolded(self, value):
        """row id ที่กางอยู่ — กรองด้วย regex เพราะค่านี้ถูกใช้ประกอบ key ต่อ"""
        out = []
        for item in value or []:
            if isinstance(item, str) and _LINE_ID_RE.match(item) and item not in out:
                out.append(item)
            if len(out) >= 300:
                break
        return out

    # ==================================================================
    # Scope / domains
    # ==================================================================
    @api.model
    def _scoped(self, model, opt):
        """ทุกคิวรีต้องผ่านตัวนี้

        ir.rule ของ stock ทุกตัวอิง ``company_ids`` ใน context (= env.companies)
        ไม่ใช่ ``company_id`` ในโดเมน ถ้าไม่ตั้ง allowed_company_ids ให้ตรงกับบริษัทที่
        ผู้ใช้ขอ รายงานจะคืนข้อมูลว่างเปล่าอย่างเงียบ ๆ เมื่อบริษัทนั้นไม่ได้ติ๊กใน switcher
        """
        return self.env[model].with_context(
            allowed_company_ids=opt["company_ids"], active_test=False
        )

    @api.model
    def _base_domain(self, opt):
        """เงื่อนไขร่วมของทุกช่วงเวลา (ยังไม่รวมเงื่อนไขวันที่)

        ตัวกรองคลัง/ที่เก็บ **ไม่อยู่ในนี้โดยตั้งใจ** — ถูกใช้ตอนปล่อย fact แทน
        เพื่อให้ "ของที่โอนออกจากคลังที่กรองไว้" ยังปรากฏเป็นรายการจ่ายออก
        """
        domain = [
            ("company_id", "in", opt["company_ids"]),
            ("state", "=", "done"),
            ("product_id.type", "=", "product"),
            ("quantity_product_uom", "!=", 0),
            # บรรทัด done ที่ไม่ถูก pick ไม่ได้ย้ายของจริง ยกเว้นการปรับปรุงยอด
            # ซึ่ง core ทำ done ด้วย picked=False ได้ (stock_move.py::_action_done)
            "|", ("picked", "=", True), ("move_id.is_inventory", "=", True),
        ]
        if not opt["include_inventory"]:
            domain.append(("move_id.is_inventory", "=", False))
        if not opt["include_scrap"]:
            domain.append(("move_id.scrapped", "=", False))
        if not opt["include_consignment"]:
            domain.append(("owner_id", "=", False))
        if opt["product_ids"]:
            domain.append(("product_id", "in", opt["product_ids"]))
        if opt["categ_ids"]:
            domain.append(("product_id.categ_id", "child_of", opt["categ_ids"]))
        if opt["lot_ids"]:
            domain.append(("lot_id", "in", opt["lot_ids"]))
        if opt["picking_type_ids"]:
            # picking_type_id บน move line เป็น compute ที่ไม่ store — ต้องผ่าน move
            domain.append(("move_id.picking_type_id", "in", opt["picking_type_ids"]))
        return domain

    @api.model
    def _svl_model(self, opt):
        """stock.valuation.layer ที่อ่านได้จริง

        ACL ของ core ให้เฉพาะ ``stock.group_stock_manager`` ผู้ใช้ที่มีสิทธิ์บัญชี
        แต่ไม่ใช่ stock manager จึงต้องอ่านผ่าน sudo() — ปลอดภัยเพราะเรียกตัวนี้
        ก็ต่อเมื่อผ่าน ``_can_see_value()`` แล้ว และ ``company_ids`` ผ่าน
        ``_resolve_company_ids()`` (ตรวจกับ user.company_ids) มาก่อนแล้วเสมอ
        """
        model = self._scoped("stock.valuation.layer", opt)
        if not self.env.user.has_group("stock.group_stock_manager"):
            model = model.sudo()
        return model

    @api.model
    def _svl_domain(self, opt):
        """เงื่อนไขของชั้นมูลค่า — ต้องตัดสิ่งเดียวกับที่ ``_base_domain`` ตัด

        ถ้าไม่ตัดให้ตรงกัน การปิด "การปรับปรุงยอด" จะทำให้จำนวนหายไปแต่มูลค่ายังอยู่
        แล้วโผล่เป็นก้อนลอยใต้ "ไม่ระบุคลัง" ซึ่งอ่านไม่รู้เรื่อง
        เงื่อนไข ``stock_move_id = False`` ต้องมีทุกครั้ง เพราะชั้นมูลค่าที่มาจากการ
        ปรับราคาต้นทุนหรือ landed cost ไม่ผูกกับ move และ dotted path จะไม่จับแถว NULL
        """
        domain = [("company_id", "in", opt["company_ids"])]
        if opt["product_ids"]:
            domain.append(("product_id", "in", opt["product_ids"]))
        if opt["categ_ids"]:
            domain.append(("product_id.categ_id", "child_of", opt["categ_ids"]))
        if not opt["include_inventory"]:
            domain += ["|", ("stock_move_id", "=", False),
                       ("stock_move_id.is_inventory", "=", False)]
        if not opt["include_scrap"]:
            domain += ["|", ("stock_move_id", "=", False),
                       ("stock_move_id.scrapped", "=", False)]
        return domain

    @api.model
    def _svl_date_domain(self, opt, operator, bound):
        """วันที่ของ SVL

        SVL **ไม่มีฟิลด์วันที่** — ``_order`` ของมันคือ ``create_date`` ซึ่งเป็นเวลาที่
        บันทึกถูกสร้าง ไม่ใช่เวลาที่ของเคลื่อนไหว การใช้ ``stock_move_id.date`` ก่อน
        ทำให้มูลค่าตกงวดเดียวกับจำนวนที่มันสังกัด (โมดูล biz_mrp_backdate ใช้กฎเดียวกัน)
        """
        if opt["value_date_basis"] == "svl_create":
            return [("create_date", operator, bound)]
        return [
            "|",
            "&", ("stock_move_id", "!=", False), ("stock_move_id.date", operator, bound),
            "&", ("stock_move_id", "=", False), ("create_date", operator, bound),
        ]

    @api.model
    def _svl_period_domain(self, opt):
        return (
            self._svl_domain(opt)
            + self._svl_date_domain(opt, ">=", opt["datetime_from"])
            + self._svl_date_domain(opt, "<=", opt["datetime_to"])
        )

    # ==================================================================
    # Dimension maps
    # ==================================================================
    @api.model
    def _load_maps(self, opt):
        """แผนที่มิติทั้งหมด อ่านครั้งเดียวต่อรายงาน

        ``location_id.warehouse_id`` ใช้เป็น groupby ของ ``_read_group`` ไม่ได้
        (ORM ปฏิเสธ dotted path) จึง groupby ที่ location แล้วแปลงเป็นคลังด้วยแผนที่นี้
        """
        locations = self._scoped("stock.location", opt).sudo().search_read(
            [], ["usage", "company_id", "warehouse_id", "complete_name", "name"]
        )
        location_map = {}
        for loc in locations:
            usage = loc["usage"]
            location_map[loc["id"]] = {
                "name": loc["name"],
                "complete_name": loc["complete_name"],
                "warehouse_id": loc["warehouse_id"][0] if loc["warehouse_id"] else 0,
                "usage": usage,
                # นับเป็นของคงคลังหรือไม่ — ตรงกับนิยามของ qty_available
                "on_hand": usage == "internal",
                # อยู่ในขอบเขตมูลค่าของบริษัทหรือไม่ — stock.location._should_be_valued()
                "valued": usage == "internal" or bool(usage == "transit" and loc["company_id"]),
            }

        warehouses = self._scoped("stock.warehouse", opt).search_read(
            [("company_id", "in", opt["company_ids"])], ["name", "code", "company_id"]
        )
        warehouse_map = {
            wh["id"]: {
                "name": wh["name"],
                "code": wh["code"],
                "company_id": wh["company_id"][0] if wh["company_id"] else 0,
            }
            for wh in warehouses
        }
        picking_types = self._scoped("stock.picking.type", opt).search_read(
            [("company_id", "in", opt["company_ids"] + [False])], ["display_name"]
        )
        return {
            "location": location_map,
            "warehouse": warehouse_map,
            "warehouse_list": [
                {"id": wh["id"], "name": wh["name"], "code": wh["code"],
                 "company_id": wh["company_id"][0] if wh["company_id"] else 0}
                for wh in warehouses
            ],
            "picking_type_list": [
                {"id": pt["id"], "name": pt["display_name"]} for pt in picking_types
            ],
            "product": {},
            "lot": {},
            "categ": {},
            "company": {
                c.id: c.name for c in self.env["res.company"].browse(opt["company_ids"])
            },
            "location_scope": self._location_scope(opt, location_map),
        }

    @api.model
    def _location_scope(self, opt, location_map):
        """เซ็ตของ location ที่ผู้ใช้อยากเห็น (None = ทุกที่)"""
        if not opt["warehouse_ids"] and not opt["location_ids"]:
            return None
        scope = set()
        if opt["warehouse_ids"]:
            for loc_id, info in location_map.items():
                if info["warehouse_id"] in opt["warehouse_ids"]:
                    scope.add(loc_id)
        if opt["location_ids"]:
            children = self._scoped("stock.location", opt).sudo().search(
                [("id", "child_of", opt["location_ids"])]
            )
            scope.update(children.ids)
        return scope

    @api.model
    def _fill_product_map(self, opt, maps, product_ids):
        missing = [p for p in product_ids if p not in maps["product"]]
        if not missing:
            return
        products = self._scoped("product.product", opt).sudo().browse(missing)
        for product in products:
            maps["product"][product.id] = {
                "name": product.name,
                "default_code": product.default_code or "",
                "categ_id": product.categ_id.id,
                "uom_name": product.uom_id.name,
                "uom_rounding": product.uom_id.rounding,
                "tracking": product.tracking,
            }
            maps["categ"].setdefault(
                product.categ_id.id,
                {"name": product.categ_id.name, "complete_name": product.categ_id.complete_name},
            )

    @api.model
    def _fill_lot_map(self, opt, maps, lot_ids):
        missing = [l for l in lot_ids if l and l not in maps["lot"]]
        if not missing:
            return
        lots = self._scoped("stock.lot", opt).sudo().search_read(
            [("id", "in", missing)], ["name", "ref"]
        )
        for lot in lots:
            maps["lot"][lot["id"]] = {"name": lot["name"], "ref": lot["ref"] or ""}

    # ==================================================================
    # Quantity ledger
    # ==================================================================
    @api.model
    def _qty_groupby(self, opt):
        groupby = ["company_id", "product_id", "location_id", "location_dest_id"]
        if opt["group_lot"]:
            groupby.append("lot_id")
        return groupby

    @api.model
    def _read_qty_groups(self, opt, phase):
        """Q1 (ยอดยกมา) / Q2 (ในงวด) — สองคิวรีหนักเพียงสองตัวของรายงาน"""
        domain = self._base_domain(opt)
        if phase == "opening":
            if opt["opening_basis"] == "none":
                return []
            domain = domain + [("date", "<", opt["datetime_from"])]
        else:
            domain = domain + [
                ("date", ">=", opt["datetime_from"]),
                ("date", "<=", opt["datetime_to"]),
            ]
        return self._scoped("stock.move.line", opt)._read_group(
            domain,
            groupby=self._qty_groupby(opt),
            aggregates=["quantity_product_uom:sum", "__count"],
        )

    @api.model
    def _fact_key(self, opt, company_id, loc_id, product_id, lot_id, maps):
        """คีย์ของ fact ที่ granularity ของการจัดกลุ่มปัจจุบัน

        location/lot เป็น 0 เมื่อระดับนั้นปิดอยู่ ทำให้การย้ายของภายในโหนดเดียวกัน
        ได้ key ต้นทาง == key ปลายทาง แล้วถูกตัดทิ้งใน ``_emit_facts``
        """
        info = maps["location"].get(loc_id) or {}
        return (
            company_id,
            info.get("warehouse_id", 0),
            product_id,
            loc_id if opt["group_location"] else 0,
            lot_id if opt["group_lot"] else 0,
        )

    @api.model
    def _emit_facts(self, rows, phase, opt, maps, nodes, shadow, stats):
        """แกะผลของ ``_read_group`` ตามลำดับ groupby แล้วส่งต่อให้ ``_emit_fact_row``"""
        has_lot = opt["group_lot"]
        for row in rows:
            if has_lot:
                company, product, loc_src, loc_dst, lot, qty, count = row
                lot_id = lot.id or 0
            else:
                company, product, loc_src, loc_dst, qty, count = row
                lot_id = 0
            self._emit_fact_row(
                company.id, product.id, loc_src.id, loc_dst.id, lot_id,
                qty or 0.0, count or 0, phase, opt, maps, nodes, shadow, stats,
            )

    @api.model
    def _emit_fact_row(self, company_id, product_id, src_id, dst_id, lot_id, qty, count,
                       phase, opt, maps, nodes, shadow, stats):
        """แปลงผลรวมหนึ่งก้อนเป็น fact 0-2 ตัว — หัวใจของสถาปัตยกรรมทั้งหมด

        กฎ (generalise มาจาก stock_account/_compute_warehouse_id):
        ที่มาเป็นของคงคลัง → ปล่อย OUT ที่โหนดต้นทาง; ที่ไปเป็นของคงคลัง → ปล่อย IN
        ที่โหนดปลายทาง; ถ้าทั้งคู่เป็นของคงคลังและตกโหนดเดียวกัน → ไม่ปล่อยอะไรเลย
        (ย้ายของในคลังเดียวกันไม่ใช่การรับหรือจ่าย)

        การ์ดสินค้ารายวันเรียกเมธอดตัวนี้ตัวเดียวกัน กฎการปล่อย fact จึงมีที่เดียว
        และตัวเลขรายวันรวมกลับได้เท่ากับรายงานหลักเสมอ
        """
        if not qty:
            return
        scope = maps["location_scope"]
        src = maps["location"].get(src_id) or {}
        dst = maps["location"].get(dst_id) or {}

        src_key = dst_key = None
        if src.get("on_hand"):
            src_key = self._fact_key(opt, company_id, src_id, product_id, lot_id, maps)
        if dst.get("on_hand"):
            dst_key = self._fact_key(opt, company_id, dst_id, product_id, lot_id, maps)
        if src_key is not None and src_key == dst_key:
            return
        if src_key is None and dst_key is None:
            return

        if src_key is not None:
            # external = ปลายทางอยู่นอกขอบเขตมูลค่าของบริษัท → มี SVL หนุนหลัง
            external = not dst.get("valued")
            if scope is None or src_id in scope:
                self._add_fact(nodes, src_key, phase, "out", qty, external, opt)
            if shadow is not None:
                self._add_fact(shadow, src_key, phase, "out", qty, external, opt)
        if dst_key is not None:
            external = not src.get("valued")
            if scope is None or dst_id in scope:
                self._add_fact(nodes, dst_key, phase, "in", qty, external, opt)
            if shadow is not None:
                self._add_fact(shadow, dst_key, phase, "in", qty, external, opt)
        # นับเฉพาะบรรทัดที่ปล่อย fact จริง — การ์ดรายวันใช้เป็นจำนวนรายการของวันนั้น
        stats["emitted_lines"] = stats.get("emitted_lines", 0) + count
        if phase == "period" and src_key is not None and dst_key is not None:
            stats["internal_lines"] = stats.get("internal_lines", 0) + count
            if src_key[K_WH] != dst_key[K_WH]:
                stats["interwarehouse_lines"] = stats.get("interwarehouse_lines", 0) + count
                stats["interwarehouse_qty"] = stats.get("interwarehouse_qty", 0.0) + qty

    @api.model
    def _add_fact(self, nodes, key, phase, direction, qty, external, opt):
        node = nodes.get(key)
        if node is None:
            if len(nodes) >= opt["max_groups"]:
                raise UserError(_(
                    "รายงานนี้มีมากกว่า %s กลุ่ม ซึ่งเกินขีดจำกัดที่ตั้งไว้\n\n"
                    "ลองกรองคลัง หมวดสินค้า หรือสินค้าให้แคบลง "
                    "หรือปิดระดับ 'ที่เก็บย่อย' / 'ล็อต-ซีเรียล'"
                ) % opt["max_groups"])
            node = nodes[key] = _zero_measures()
        if phase == "opening":
            node["opening_qty"] += qty if direction == "in" else -qty
            return
        if direction == "in":
            node["in_qty"] += qty
            if external:
                node["in_qty_ext"] += qty
        else:
            node["out_qty"] += qty
            if external:
                node["out_qty_ext"] += qty

    @api.model
    def _ledger_nodes(self, opt, maps, stats):
        """สร้าง fact table แล้วพับเป็นโหนดใบ {key: measures}

        เมื่อผู้ใช้กรองคลัง/ที่เก็บ จะสร้าง "ชุดเงา" ที่ไม่ผ่านตัวกรองไว้ด้วย เพื่อใช้เป็น
        **ตัวหาร** ของการกระจายมูลค่า — ไม่งั้นกรองคลังเดียวแล้วคลังนั้นจะได้รับมูลค่า
        SVL ของทั้งสินค้าไปทั้งก้อน ซึ่งเป็นการตีมูลค่าสูงเกินจริง
        """
        nodes = {}
        scoped = maps["location_scope"] is not None
        shadow = {} if scoped else None
        for phase in ("opening", "period"):
            self._emit_facts(
                self._read_qty_groups(opt, phase), phase, opt, maps, nodes, shadow, stats
            )

        product_ids, lot_ids = set(), set()
        for target in (nodes, shadow):
            if target is None:
                continue
            for key, node in target.items():
                node["closing_qty"] = node["opening_qty"] + node["in_qty"] - node["out_qty"]
                if target is nodes:
                    product_ids.add(key[K_PRODUCT])
                    if key[K_LOT]:
                        lot_ids.add(key[K_LOT])
        self._fill_product_map(opt, maps, sorted(product_ids))
        self._fill_lot_map(opt, maps, sorted(lot_ids))
        return nodes, (shadow if scoped else nodes)

    # ==================================================================
    # Value ledger
    # ==================================================================
    @api.model
    def _read_svl_buckets(self, opt):
        """Q3-Q7 — มูลค่าแม่นยำที่ระดับ (บริษัท, สินค้า)

        ``unit_cost`` มี ``group_operator=None`` จึงรวมยอดไม่ได้เด็ดขาด ต้นทุนเฉลี่ย
        คำนวณเป็น SUM(value)/SUM(quantity) เสมอ
        """
        svl = self._svl_model(opt)
        base = self._svl_domain(opt)
        period = self._svl_period_domain(opt)
        buckets = {"opening": {}, "in": {}, "out": {}, "adj": {}, "control": {}}

        if opt["opening_basis"] != "none":
            for company, product, value, qty in svl._read_group(
                base + self._svl_date_domain(opt, "<", opt["datetime_from"]),
                groupby=["company_id", "product_id"],
                aggregates=["value:sum", "quantity:sum"],
            ):
                buckets["opening"][(company.id, product.id)] = (value or 0.0, qty or 0.0)

        for bucket, extra in (
            ("in", [("quantity", ">", 0)]),
            ("out", [("quantity", "<", 0)]),
            ("adj", [("quantity", "=", 0)]),
        ):
            for company, product, value, qty in svl._read_group(
                period + extra,
                groupby=["company_id", "product_id"],
                aggregates=["value:sum", "quantity:sum"],
            ):
                # ฝั่งจ่ายออกเก็บเป็นค่าบวก (ธรรมเนียมรับ/จ่ายไทย — ไม่มีเลขติดลบในตาราง)
                buckets[bucket][(company.id, product.id)] = (
                    -(value or 0.0) if bucket == "out" else (value or 0.0),
                    abs(qty or 0.0),
                )

        for company, value, count in svl._read_group(
            period, groupby=["company_id"], aggregates=["value:sum", "__count"]
        ):
            buckets["control"][company.id] = (value or 0.0, count or 0)
        return buckets

    @api.model
    def _allocate_value(self, nodes, denominators, svl, opt, stats):
        """กระจายมูลค่า SVL ลงต้นไม้ตามสัดส่วนจำนวน แล้วประมาณมูลค่าการโอนภายใน

        SVL ไม่มีมิติคลัง/ที่เก็บ/ล็อต มูลค่าต่ำกว่าระดับสินค้าจึงเป็นการเฉลี่ยเสมอ
        แต่ **ผลรวมยังตรงกับ SVL เป๊ะโดยโครงสร้าง** เพราะเศษที่กระจายไม่ลงถูกดันไป
        อยู่ในแถว value_adj ของสินค้านั้นแทนที่จะหายไปเฉย ๆ
        """
        by_product = {}
        for key, node in nodes.items():
            by_product.setdefault((key[K_COMPANY], key[K_PRODUCT]), []).append(node)
        denom_by_product = by_product
        if denominators is not nodes:
            denom_by_product = {}
            for key, node in denominators.items():
                denom_by_product.setdefault((key[K_COMPANY], key[K_PRODUCT]), []).append(node)

        # SVL อาจมีสินค้าที่ไม่มีความเคลื่อนไหวเลยในงวด (เช่นปรับมูลค่าล้วน ๆ) ถ้าไม่ดึง
        # เข้ามาด้วย มูลค่าก้อนนั้นจะหายไปเงียบ ๆ และการกระทบยอดกับ SVL จะพังทันที
        # ทำเฉพาะตอนไม่ได้กรองคลัง/ที่เก็บ เพราะรายงานที่กรองแล้วเป็นเพียงส่วนย่อยอยู่แล้ว
        if denominators is nodes:
            for bucket in ("opening", "in", "out", "adj"):
                for pair in svl.get(bucket) or {}:
                    by_product.setdefault(pair, [])

        exact = denominators is nodes
        imputed_net = 0.0
        imputed_abs = 0.0
        for (company_id, product_id), group in by_product.items():
            opening_value, _opening_qty = svl["opening"].get((company_id, product_id), (0.0, 0.0))
            in_value, in_qty_svl = svl["in"].get((company_id, product_id), (0.0, 0.0))
            out_value, _out_qty = svl["out"].get((company_id, product_id), (0.0, 0.0))
            adj_value, _adj_qty = svl["adj"].get((company_id, product_id), (0.0, 0.0))

            spread = (
                (opening_value, "opening_qty", "opening_value"),
                (in_value, "in_qty_ext", "in_value_ext"),
                (out_value, "out_qty_ext", "out_value_ext"),
                (adj_value, "closing_qty", "adj_value"),
            )
            denom_group = denom_by_product.get((company_id, product_id), group)
            for amount, weight_key, target_key in spread:
                self._spread(nodes, group, denom_group, amount, weight_key, target_key,
                             company_id, product_id, exact)

            for node in group:
                node["in_value"] = node["in_value_ext"]
                node["out_value"] = node["out_value_ext"]

            if opt["value_mode"] == "imputed":
                # ต้นทุนต่อหน่วยของงวด ใช้ตีมูลค่าการโอนภายในทั้งสองขาด้วยตัวเลขเดียวกัน
                # ทั้งคู่จึงหักล้างกันที่ระดับบริษัท และการกระทบยอด SVL ยังเป็นจริง
                base_value = opening_value + in_value + adj_value
                base_qty = sum(n["opening_qty"] for n in group) + in_qty_svl
                unit_cost = base_value / base_qty if base_qty else 0.0
                if unit_cost:
                    for node in group:
                        internal_in = node["in_qty"] - node["in_qty_ext"]
                        internal_out = node["out_qty"] - node["out_qty_ext"]
                        node["in_value"] += internal_in * unit_cost
                        node["out_value"] += internal_out * unit_cost
                        imputed_net += (internal_in - internal_out) * unit_cost
                        imputed_abs += (internal_in + internal_out) * unit_cost

            for node in group:
                node["closing_value"] = (
                    node["opening_value"] + node["in_value"]
                    - node["out_value"] + node["adj_value"]
                )
        stats["imputed_net"] = imputed_net
        stats["imputed_abs"] = imputed_abs

    @api.model
    def _spread(self, nodes, group, denom_group, amount, weight_key, target_key,
                company_id, product_id, exact):
        """กระจาย ``amount`` ให้โหนดตามน้ำหนัก ``weight_key``

        ตัวหารเป็นศูนย์ (เช่นการปรับมูลค่าสินค้าที่ไม่มีจำนวนเคลื่อนไหวเลยในงวด) →
        ยอดทั้งก้อนไปอยู่โหนด "ไม่ระบุคลัง" ของสินค้านั้น ผลรวมจึงยังตรงกับ SVL
        เป๊ะ และผู้ใช้เห็นว่ามีมูลค่าที่ระบุคลังไม่ได้อยู่เท่าไร แทนที่จะหายไปเงียบ ๆ
        """
        if not amount:
            return
        total = sum(max(node[weight_key], 0.0) for node in denom_group)
        if not total:
            if not exact:
                # รายงานถูกกรองไว้ มูลค่าที่ระบุที่ไม่ได้จึงไม่ใช่ของขอบเขตนี้
                return
            fallback = self._unassigned_node(nodes, group, company_id, product_id)
            fallback[target_key] += amount
            return
        allocated = 0.0
        last = None
        for node in group:
            weight = max(node[weight_key], 0.0)
            if not weight:
                continue
            share = amount * weight / total
            node[target_key] += share
            allocated += share
            last = node
        # ยัดเศษปัดเศษเข้าโหนดสุดท้าย ผลรวมจึงเท่ากับ SVL แบบบิตต่อบิต
        # (ทำได้เฉพาะรายงานที่ไม่ได้กรองคลัง ซึ่งครอบสินค้านั้นทั้งหมดจริง)
        if exact and last is not None and allocated != amount:
            last[target_key] += amount - allocated

    @api.model
    def _unassigned_node(self, nodes, group, company_id, product_id):
        """โหนดรับมูลค่าที่ระบุคลังไม่ได้ — คลัง/ที่เก็บ/ล็อต = 0 ("ไม่ระบุ")"""
        key = (company_id, 0, product_id, 0, 0)
        node = nodes.get(key)
        if node is None:
            node = nodes[key] = _zero_measures()
            group.append(node)
        elif node not in group:
            group.append(node)
        return node

    # ==================================================================
    # Tree
    # ==================================================================
    @api.model
    def _node_path(self, key, opt, maps):
        """คืน [(level_type, res_id), ...] ตามลำดับระดับที่ผู้ใช้เลือก"""
        product = maps["product"].get(key[K_PRODUCT], {})
        values = {
            "company": key[K_COMPANY],
            "wh": key[K_WH],
            "categ": product.get("categ_id") or 0,
            "product": key[K_PRODUCT],
            "loc": key[K_LOC],
            "lot": key[K_LOT],
        }
        return [(level, values[level]) for level in opt["levels"]]

    @api.model
    def _node_label(self, level, res_id, maps):
        """(code, name, sub) ของโหนดหนึ่ง"""
        if level == "company":
            return "", maps["company"].get(res_id, ""), ""
        if level == "wh":
            wh = maps["warehouse"].get(res_id)
            if not wh:
                return "", _("ไม่ระบุคลัง"), ""
            return wh["code"] or "", wh["name"], ""
        if level == "categ":
            categ = maps["categ"].get(res_id, {})
            return "", categ.get("name", ""), categ.get("complete_name", "")
        if level == "product":
            product = maps["product"].get(res_id, {})
            code = product.get("default_code") or ""
            return (
                "[%s]" % code if code else "",
                product.get("name", ""),
                product.get("uom_name", ""),
            )
        if level == "loc":
            loc = maps["location"].get(res_id)
            if not loc:
                return "", _("ไม่ระบุที่เก็บ"), ""
            return "", loc["name"], loc["complete_name"]
        lot = maps["lot"].get(res_id)
        if not lot:
            return "", _("ไม่ระบุล็อต"), ""
        return "", lot["name"], lot.get("ref", "")

    @api.model
    def _build_tree(self, nodes, opt, maps):
        """pivot โหนดใบเป็นต้นไม้ N ระดับ แล้วแบนเป็นลิสต์เรียงพร้อมแสดง"""
        levels = opt["levels"]
        tree = {}
        for key, measures in nodes.items():
            path = self._node_path(key, opt, maps)
            cursor = tree
            for depth, (level, res_id) in enumerate(path):
                slot = cursor.setdefault(
                    (level, res_id),
                    {"level": level, "res_id": res_id, "measures": _zero_measures(),
                     "children": {}, "keys": []},
                )
                for mkey in MEASURE_KEYS:
                    slot["measures"][mkey] += measures[mkey]
                if depth == len(path) - 1:
                    slot["keys"].append(key)
                cursor = slot["children"]

        lines = []
        totals = _zero_measures()
        rounding = self._rounding(opt)
        for slot in self._sorted_slots(tree, maps):
            branch = self._emit_slot(slot, "", 0, opt, maps, rounding, "")
            if not branch:
                continue
            branch[0]["counts_to_total"] = True
            for mkey in MEASURE_KEYS:
                totals[mkey] += branch[0][mkey]
            lines.extend(branch)
        totals = self._round_measures(totals, opt, rounding)
        totals.update({
            "kind": "grand_total",
            "id": "grand_total",
            "name": _("รวมทั้งสิ้น"),
            "code": "", "sub": "", "uom_name": "", "level": 0,
            "counts_to_total": False,
            "avg_cost": self._avg_cost(totals),
        })
        return lines, totals

    @api.model
    def _sorted_slots(self, mapping, maps):
        def sort_key(slot):
            code, name, _sub = self._node_label(slot["level"], slot["res_id"], maps)
            return (code or "￿", name or "")
        return sorted(mapping.values(), key=sort_key)

    @api.model
    def _emit_slot(self, slot, parent_id, depth, opt, maps, rounding, uom_name):
        """แปลงโหนดหนึ่งเป็นแถว (พร้อมลูก ๆ ถ้ากางอยู่)

        ``uom_name`` ถูกส่งต่อลงมาจากระดับสินค้าที่อยู่เหนือขึ้นไป ทุกแถวตั้งแต่ระดับ
        สินค้าลงไป (ที่เก็บ, ล็อต, รายการเคลื่อนไหว) จึงแสดงหน่วยเดียวกันได้ในคอลัมน์เดียว
        """
        level, res_id = slot["level"], slot["res_id"]
        row_id = "%s/%s-%s" % (parent_id, LEVEL_PREFIX[level], res_id) if parent_id \
            else "%s-%s" % (LEVEL_PREFIX[level], res_id)
        measures = slot["measures"]
        if not self._keep_row(measures, opt, rounding):
            return []

        code, name, sub = self._node_label(level, res_id, maps)
        if level == "product":
            uom_name = maps["product"].get(res_id, {}).get("uom_name") or ""
        children = self._sorted_slots(slot["children"], maps) if slot["children"] else []
        unfolded = depth < opt["unfold_level"] or row_id in opt["unfolded"]
        is_leaf = not children

        line = self._round_measures(dict(measures), opt, rounding)
        line.update({
            "kind": "group",
            "id": row_id,
            "parent_id": parent_id or False,
            "level": depth,
            "counts_to_total": False,
            "group_type": level,
            "res_model": LEVEL_MODEL[level],
            "res_id": res_id,
            "code": code,
            "name": name,
            "sub": sub,
            "uom_name": uom_name,
            "unfoldable": True,
            "unfolded": unfolded,
            "child_count": len(children),
            "avg_cost": self._avg_cost(measures),
            "flag": self._flag(measures, opt, rounding),
            "leaf_keys": slot["keys"] if is_leaf else [],
            "code_is_name": False,
        })
        rows = [line]
        if not unfolded:
            return rows

        for child in children:
            rows.extend(
                self._emit_slot(child, row_id, depth + 1, opt, maps, rounding, uom_name)
            )
        if children:
            total = self._round_measures(dict(measures), opt, rounding)
            total.update({
                "kind": "group_total",
                "id": "%s/total" % row_id,
                "parent_id": row_id,
                "level": depth,
                "counts_to_total": False,
                "group_type": level,
                "res_model": False, "res_id": False,
                "code": "", "name": _("รวม %s") % name, "sub": "",
                "uom_name": uom_name,
                "unfoldable": False, "unfolded": False, "child_count": 0,
                "avg_cost": self._avg_cost(measures),
                "flag": "ok", "leaf_keys": [], "code_is_name": False,
            })
            rows.append(total)
        return rows

    @api.model
    def _keep_row(self, measures, opt, rounding):
        if opt["display_product"] == "all":
            return True
        # แถวที่ยังถือมูลค่าอยู่ต้องไม่ถูกซ่อน ไม่งั้นยอดรวมจะไม่กระทบกับ SVL อีกต่อไป
        if any(measures[key] for key in VAL_KEYS):
            return True
        moved = not (
            float_is_zero(measures["in_qty"], precision_rounding=rounding)
            and float_is_zero(measures["out_qty"], precision_rounding=rounding)
        )
        if opt["display_product"] == "movement":
            return moved or not (
                float_is_zero(measures["opening_qty"], precision_rounding=rounding)
                and float_is_zero(measures["closing_qty"], precision_rounding=rounding)
            )
        return not float_is_zero(measures["closing_qty"], precision_rounding=rounding) or moved

    @api.model
    def _rounding(self, opt):
        return 10 ** -opt["qty_precision"]

    @api.model
    def _round_measures(self, measures, opt, rounding):
        decimals = self.env["res.company"].browse(opt["company_id"]).currency_id.decimal_places
        out = {}
        for key in QTY_KEYS + EXT_QTY_KEYS:
            out[key] = float_round(measures[key], precision_rounding=rounding)
        for key in VAL_KEYS + EXT_VAL_KEYS:
            out[key] = round(measures[key], decimals) if opt["show_value"] else 0.0
        return out

    @api.model
    def _avg_cost(self, measures):
        qty = measures["closing_qty"]
        if not qty:
            return None
        return measures["closing_value"] / qty

    @api.model
    def _flag(self, measures, opt, rounding):
        if measures["closing_qty"] < 0 and not float_is_zero(
            measures["closing_qty"], precision_rounding=rounding
        ):
            return "negative"
        if opt["show_value"] and measures["closing_qty"] and not measures["closing_value"]:
            return "no_value"
        return "ok"

    # ==================================================================
    # Detail rows + running balance
    # ==================================================================
    @api.model
    def _attach_details(self, lines, opt, maps, stats):
        """ดึงรายการเคลื่อนไหวเฉพาะใบที่กางอยู่ แล้วคำนวณยอดคงเหลือสะสม"""
        leaves = [
            line for line in lines
            if line["kind"] == "group" and line.get("leaf_keys")
            and (opt["detail_mode"] == "all" or line["unfolded"])
        ]
        if not leaves:
            return lines
        leaves = leaves[: opt["max_detail_leaves"]]

        out = []
        budget = opt["detail_total_limit"]
        details_by_parent = {}
        for leaf in leaves:
            if budget <= 0:
                break
            rows, truncated = self._read_leaf_details(leaf, opt, maps, min(opt["detail_limit"], budget))
            budget -= len(rows)
            stats["detail_rows"] += len(rows)
            if truncated:
                stats["truncated_leaves"] += 1
            details_by_parent[leaf["id"]] = self._running_balance(leaf, rows, opt, truncated)

        for line in lines:
            out.append(line)
            for detail in details_by_parent.get(line["id"], []):
                out.append(detail)
        return out

    @api.model
    def _leaf_location_ids(self, leaf, opt, maps):
        """location ที่นับเป็นของโหนดใบนี้

        โหมดงบรวมยุบหลายบริษัทเป็นแถวเดียว ใบหนึ่งจึงถือได้หลายคีย์ — แต่ระดับ
        คลัง/ที่เก็บ/ล็อต อยู่ในเส้นทางของต้นไม้แล้ว จึงคงที่ทุกคีย์ มีแต่บริษัทที่ต่างกันได้
        """
        keys = leaf["leaf_keys"]
        loc_ids = {key[K_LOC] for key in keys if key[K_LOC]}
        if loc_ids:
            children = self._scoped("stock.location", opt).sudo().search(
                [("id", "child_of", sorted(loc_ids))]
            )
            return children.ids
        warehouse_ids = {key[K_WH] for key in keys}
        return [
            loc_id for loc_id, info in maps["location"].items()
            if info["warehouse_id"] in warehouse_ids and info["on_hand"]
        ]

    @api.model
    def _read_leaf_details(self, leaf, opt, maps, limit):
        """Q8 — บรรทัดการเคลื่อนไหวของใบเดียว เรียงตามเอกสาร (date, id)"""
        keys = set(leaf["leaf_keys"])
        first = leaf["leaf_keys"][0]
        locs = self._leaf_location_ids(leaf, opt, maps)
        domain = self._base_domain(opt) + [
            ("date", ">=", opt["datetime_from"]),
            ("date", "<=", opt["datetime_to"]),
            ("company_id", "in", sorted({key[K_COMPANY] for key in keys})),
            ("product_id", "=", first[K_PRODUCT]),
            "|", ("location_id", "in", locs), ("location_dest_id", "in", locs),
        ]
        if opt["group_lot"]:
            domain.append(("lot_id", "=", first[K_LOT] or False))

        model = self._scoped("stock.move.line", opt)
        records = model.search_read(
            domain,
            ["date", "reference", "product_uom_id", "quantity_product_uom", "lot_id",
             "location_id", "location_dest_id", "picking_id", "move_id", "owner_id",
             "company_id", "product_id"],
            order="date, id", limit=limit + 1,
        )
        truncated = len(records) > limit
        records = records[:limit]
        if not records:
            return [], False

        move_ids = [r["move_id"][0] for r in records if r["move_id"]]
        moves = {
            m["id"]: m
            for m in self._scoped("stock.move", opt).sudo().search_read(
                [("id", "in", move_ids)],
                ["picking_type_id", "is_inventory", "scrapped", "origin", "partner_id"],
            )
        } if move_ids else {}

        rows = []
        for record in records:
            src_id = record["location_id"][0]
            dst_id = record["location_dest_id"][0]
            lot_id = record["lot_id"][0] if record["lot_id"] else 0
            company_id = record["company_id"][0]
            product_id = record["product_id"][0]
            src = maps["location"].get(src_id) or {}
            dst = maps["location"].get(dst_id) or {}
            # ใช้กฎเดียวกับ _emit_facts เป๊ะ ๆ ใบหนึ่งจึงไม่มีวันแสดงบรรทัดที่ไม่ได้เป็นของมัน
            src_key = (
                self._fact_key(opt, company_id, src_id, product_id, lot_id, maps)
                if src.get("on_hand") else None
            )
            dst_key = (
                self._fact_key(opt, company_id, dst_id, product_id, lot_id, maps)
                if dst.get("on_hand") else None
            )
            if src_key is not None and src_key == dst_key:
                continue
            if dst_key in keys:
                direction, external = "in", not src.get("valued")
            elif src_key in keys:
                direction, external = "out", not dst.get("valued")
            else:
                continue
            move = moves.get(record["move_id"][0]) if record["move_id"] else {}
            rows.append({
                "record": record, "move": move or {},
                "direction": direction, "external": external,
                "src": src, "dst": dst,
            })
        return rows, truncated

    @api.model
    def _running_balance(self, leaf, rows, opt, truncated):
        """ยอดคงเหลือสะสม — คอลัมน์ที่ทำให้รายงานนี้เป็น "การ์ด" ไม่ใช่แค่ตารางสรุป"""
        rounding = self._rounding(opt)
        decimals = self.env["res.company"].browse(opt["company_id"]).currency_id.decimal_places
        unit_in = (leaf["in_value"] / leaf["in_qty"]) if leaf["in_qty"] else 0.0
        unit_out = (leaf["out_value"] / leaf["out_qty"]) if leaf["out_qty"] else 0.0

        balance_qty = leaf["opening_qty"]
        balance_value = leaf["opening_value"]
        shown_in = shown_out = 0.0
        details = []
        for row in rows:
            record, move = row["record"], row["move"]
            qty = record["quantity_product_uom"] or 0.0
            line = _zero_measures()
            if row["direction"] == "in":
                line["in_qty"] = qty
                line["in_value"] = line["in_value_ext"] = qty * unit_in if opt["show_value"] else 0.0
                if row["external"]:
                    line["in_qty_ext"] = qty
                balance_qty += qty
                balance_value += line["in_value"]
                shown_in += qty
            else:
                line["out_qty"] = qty
                line["out_value"] = line["out_value_ext"] = qty * unit_out if opt["show_value"] else 0.0
                if row["external"]:
                    line["out_qty_ext"] = qty
                balance_qty -= qty
                balance_value -= line["out_value"]
                shown_out += qty
            line = self._round_measures(line, opt, rounding)
            unit_cost = None
            if opt["show_value"] and qty:
                unit_cost = (line["in_value"] or line["out_value"]) / qty
            line.update({
                "kind": "move",
                "id": "%s/mvl-%s" % (leaf["id"], record["id"]),
                "parent_id": leaf["id"],
                "level": leaf["level"] + 1,
                "counts_to_total": False,
                "group_type": False,
                "res_model": "stock.move.line", "res_id": record["id"],
                "move_line_id": record["id"],
                "move_id": record["move_id"][0] if record["move_id"] else False,
                "picking_id": record["picking_id"][0] if record["picking_id"] else False,
                "date": record["date"] and fields.Datetime.to_string(record["date"]) or "",
                "date_display": self.format_report_datetime(
                    record["date"], opt["tz"], opt["date_format"]
                ),
                "code": record["reference"] or "",
                "name": (record["picking_id"] and record["picking_id"][1])
                        or move.get("origin") or record["reference"] or "",
                # ใช้บอกฝั่งแสดงผลว่าเลขที่เอกสารซ้ำกับชื่อรายการหรือไม่
                "code_is_name": (
                    (record["picking_id"] and record["picking_id"][1])
                    or move.get("origin") or record["reference"] or ""
                ) == (record["reference"] or ""),
                "sub": "%s → %s" % (
                    row["src"].get("complete_name", ""), row["dst"].get("complete_name", "")
                ),
                "picking_type": (move.get("picking_type_id") or [0, ""])[1],
                "location_id": record["location_id"][0],
                "location_name": row["src"].get("complete_name", ""),
                "location_dest_id": record["location_dest_id"][0],
                "location_dest_name": row["dst"].get("complete_name", ""),
                "lot_id": record["lot_id"][0] if record["lot_id"] else False,
                "lot_name": record["lot_id"][1] if record["lot_id"] else "",
                "partner_name": (move.get("partner_id") or [0, ""])[1],
                "uom_name": record["product_uom_id"][1] if record["product_uom_id"] else "",
                "direction": row["direction"],
                "external": row["external"],
                "is_inventory": bool(move.get("is_inventory")),
                "is_scrap": bool(move.get("scrapped")),
                "unit_cost": round(unit_cost, decimals) if unit_cost is not None else None,
                "balance_qty": float_round(balance_qty, precision_rounding=rounding),
                "balance_value": round(balance_value, decimals) if opt["show_value"] else 0.0,
                "unfoldable": False, "unfolded": False, "child_count": 0,
                "avg_cost": None, "flag": "ok", "leaf_keys": [],
            })
            details.append(line)

        if truncated:
            # แถวปิดท้ายถือยอดที่เหลือไว้ ยอดคงเหลือสะสมจึงยังจบที่ยอดจริงของโหนด
            remaining_in = max(leaf["in_qty"] - shown_in, 0.0)
            remaining_out = max(leaf["out_qty"] - shown_out, 0.0)
            line = _zero_measures()
            line["in_qty"] = remaining_in
            line["out_qty"] = remaining_out
            if opt["show_value"]:
                line["in_value"] = remaining_in * unit_in
                line["out_value"] = remaining_out * unit_out
            line = self._round_measures(line, opt, rounding)
            line.update({
                "kind": "more",
                "id": "%s/more" % leaf["id"],
                "parent_id": leaf["id"],
                "level": leaf["level"] + 1,
                "counts_to_total": False,
                "group_type": False,
                "res_model": False, "res_id": False,
                "code": "",
                "name": _("…แสดง %s รายการแรกเท่านั้น กดที่แถวเพื่อดูทั้งหมด") % len(details),
                "sub": "", "shown": len(details),
                "uom_name": details[-1].get("uom_name", "") if details else "",
                "date": "", "date_display": "",
                "direction": False, "unit_cost": None,
                "balance_qty": leaf["closing_qty"],
                "balance_value": leaf["closing_value"] if opt["show_value"] else 0.0,
                "unfoldable": False, "unfolded": False, "child_count": 0,
                "avg_cost": None, "flag": "ok", "leaf_keys": [], "code_is_name": False,
            })
            details.append(line)
        return details

    @api.model
    def _strip_internal(self, lines):
        """``leaf_keys`` เป็นข้อมูลภายในของเครื่องยนต์ ไม่ควรข้าม RPC ไปหา client"""
        for line in lines:
            line.pop("leaf_keys", None)

    # ==================================================================
    # Product card (การ์ดสินค้ารายวัน)
    # ==================================================================
    @api.model
    def _card_options(self, options, product_id):
        """options ของการ์ด — สินค้าตัวเดียว ปิดระดับย่อยที่การ์ดไม่ใช้

        ตัวกรองอื่นของหน้าหลัก (คลัง, บริษัท, ชนิดรายการ, ช่วงเวลา, วิธีคิดมูลค่า)
        ถูกยกมาทั้งหมด การ์ดจึงเป็นการซูมเข้าไปดูสินค้าตัวเดียวของ "รายงานฉบับเดิม"
        ไม่ใช่รายงานคนละฉบับที่บังเอิญหน้าตาคล้ายกัน
        """
        if not product_id:
            raise UserError(_("ต้องระบุสินค้าก่อนจึงจะเปิดการ์ดสินค้าได้"))
        opt = dict(options or {})
        opt.update({
            "product_ids": [int(product_id)],
            "categ_ids": [],
            "lot_ids": [],
            "group_location": False,
            "group_lot": False,
            "detail_mode": "none",
            "display_product": "all",
        })
        return self._normalize_options(opt)

    @api.model
    def _as_day(self, value):
        """ค่า ``date:day`` ของ _read_group — คืนเป็น ``date`` เสมอ

        ORM คืนค่ามาเป็น date, datetime หรือสตริงได้แล้วแต่รุ่น จึงบีบให้เหลือชนิดเดียว
        ก่อนใช้เป็นคีย์ ไม่งั้นวันเดียวกันจะกลายเป็นสองแถวเงียบ ๆ
        """
        if not value:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return fields.Date.to_date(str(value)[:10])

    @api.model
    def _local_day(self, stamp, zone):
        """วันตามเขตเวลาผู้ใช้ของ datetime แบบ naive-UTC"""
        if not stamp:
            return None
        value = fields.Datetime.to_datetime(stamp)
        return pytz.UTC.localize(value).astimezone(zone).date()

    @api.model
    def _read_day_groups(self, opt):
        """คิวรีเดียวของการ์ด — ผลรวมจำนวนในงวด ซอยเพิ่มอีกหนึ่งมิติคือ "วัน"

        ``with_context(tz=...)`` จำเป็น เพราะ ``date`` เป็น Datetime เก็บ UTC
        ถ้าไม่ตั้งเขตเวลาให้ตรงกับ ``_period_bounds()`` ของที่รับเข้าตอน 4 ทุ่ม
        เวลาไทยจะตกไปอยู่วันถัดไป — ขอบงวดกับแถวรายวันจะเล่าคนละเรื่องกันทันที
        """
        domain = self._base_domain(opt) + [
            ("date", ">=", opt["datetime_from"]),
            ("date", "<=", opt["datetime_to"]),
        ]
        model = self._scoped("stock.move.line", opt).with_context(tz=opt["tz"])
        return model._read_group(
            domain,
            groupby=self._qty_groupby(opt) + ["date:day"],
            aggregates=["quantity_product_uom:sum", "__count"],
        )

    @api.model
    def _read_svl_days(self, opt):
        """มูลค่า SVL ของงวด ซอยตามวัน

        groupby รายวันตรง ๆ ทำไม่ได้ เพราะวันของชั้นมูลค่าอยู่ที่ ``stock_move_id.date``
        ซึ่งเป็น dotted path ที่ ``_read_group`` ปฏิเสธ — การ์ดจำกัดสินค้าไว้ตัวเดียวแล้ว
        จำนวนแถวจึงน้อยพอที่จะอ่านมาซอยใน Python ได้ กฎการเลือกวันต้องตรงกับ
        ``_svl_date_domain()`` เป๊ะ ไม่งั้นมูลค่าจะตกคนละงวดกับที่โดเมนคัดมา
        """
        rows = self._svl_model(opt).search_read(
            self._svl_period_domain(opt),
            ["quantity", "value", "stock_move_id", "create_date"],
        )
        move_dates = {}
        if opt["value_date_basis"] != "svl_create":
            move_ids = [r["stock_move_id"][0] for r in rows if r["stock_move_id"]]
            if move_ids:
                move_dates = {
                    m["id"]: m["date"]
                    for m in self._scoped("stock.move", opt).sudo().search_read(
                        [("id", "in", move_ids)], ["date"]
                    )
                }

        zone = pytz.timezone(opt["tz"])
        buckets = {}
        for row in rows:
            stamp = row["create_date"]
            if opt["value_date_basis"] != "svl_create" and row["stock_move_id"]:
                stamp = move_dates.get(row["stock_move_id"][0]) or row["create_date"]
            day = self._local_day(stamp, zone)
            if not day:
                continue
            bucket = buckets.setdefault(day, {
                "in_value": 0.0, "in_qty": 0.0,
                "out_value": 0.0, "out_qty": 0.0, "adj_value": 0.0,
            })
            qty = row["quantity"] or 0.0
            value = row["value"] or 0.0
            if qty > 0:
                bucket["in_value"] += value
                bucket["in_qty"] += qty
            elif qty < 0:
                # ฝั่งจ่ายออกเก็บเป็นค่าบวก (ธรรมเนียมเดียวกับ _read_svl_buckets)
                bucket["out_value"] += -value
                bucket["out_qty"] += -qty
            else:
                bucket["adj_value"] += value
        return buckets

    @api.model
    def _day_facts(self, opt, maps):
        """ซอย fact ของงวดออกเป็นรายวัน ด้วยกฎการปล่อย fact ตัวเดียวกับรายงานหลัก"""
        per_day, counts = {}, {}
        has_lot = opt["group_lot"]
        for row in self._read_day_groups(opt):
            if has_lot:
                company, product, loc_src, loc_dst, lot, day, qty, count = row
                lot_id = lot.id or 0
            else:
                company, product, loc_src, loc_dst, day, qty, count = row
                lot_id = 0
            day = self._as_day(day)
            if not day:
                continue
            stats = {}
            self._emit_fact_row(
                company.id, product.id, loc_src.id, loc_dst.id, lot_id,
                qty or 0.0, count or 0, "period", opt, maps,
                per_day.setdefault(day, {}), None, stats,
            )
            counts[day] = counts.get(day, 0) + stats.get("emitted_lines", 0)

        days = []
        for day in sorted(per_day):
            measures = _zero_measures()
            for node in per_day[day].values():
                for key in ("in_qty", "out_qty") + EXT_QTY_KEYS:
                    measures[key] += node[key]
            if not (measures["in_qty"] or measures["out_qty"]):
                continue
            measures["day"] = day
            measures["move_count"] = counts.get(day, 0)
            days.append(measures)
        return days

    @api.model
    def _spread_to_days(self, weights, target):
        """กระจาย ``target`` ให้แต่ละวันตามน้ำหนัก แล้วยัดเศษเข้าวันสุดท้ายที่มีน้ำหนัก

        ผลรวมจึงเท่ากับ ``target`` แบบบิตต่อบิต — หลักการเดียวกับ ``_spread()``
        ที่ระดับโหนด ส่วนที่กระจายไม่ลง (น้ำหนักรวมเป็นศูนย์) ถูกคืนกลับให้ผู้เรียก
        ไปลงคอลัมน์ปรับมูลค่า ไม่ใช่ปล่อยให้หายเงียบ ๆ
        """
        values = [0.0] * len(weights)
        if not target:
            return values, 0.0
        # clamp เหมือน _spread() ระดับโหนด — ราคาต่อหน่วยรายวันติดลบได้ (SVL
        # ปรับมูลค่าย้อนหลัง) น้ำหนักลบจะหักล้างกันจน total ใกล้ศูนย์แล้ว
        # share ระเบิดทั้งที่ผลรวมยังตรงกับ target พอดี
        total = sum(max(weight, 0.0) for weight in weights)
        if not total:
            return values, target
        allocated, last = 0.0, -1
        for index, weight in enumerate(weights):
            weight = max(weight, 0.0)
            if not weight:
                continue
            share = target * weight / total
            values[index] = share
            allocated += share
            last = index
        if last >= 0 and allocated != target:
            values[last] += target - allocated
        return values, 0.0

    @api.model
    def _day_values(self, opt, days, totals, svl_days):
        """ลงมูลค่าให้แถวรายวัน — ราคาต่อหน่วยเป็นของ "วันนั้น" จริงจาก SVL

        ยอดรวมของทุกวันถูกบังคับให้เท่ากับยอดของสินค้าที่เครื่องยนต์คำนวณไว้แล้ว
        (``totals``) เสมอ ทั้งกรณีปกติและกรณีที่กรองคลัง (ซึ่งมูลค่าเป็นส่วนแบ่ง
        ตามสัดส่วนจำนวน) ราคาต่อหน่วยที่แสดงยังเป็นราคาจริงของวันนั้นไม่ถูกย่อ/ขยาย
        """
        for day in days:
            bucket = svl_days.get(day["day"]) or {}
            in_qty = bucket.get("in_qty") or 0.0
            out_qty = bucket.get("out_qty") or 0.0
            day["unit_in"] = (bucket["in_value"] / in_qty) if in_qty else None
            day["unit_out"] = (bucket["out_value"] / out_qty) if out_qty else None
            day["svl_adj"] = bucket.get("adj_value") or 0.0

        # ส่วนที่มี SVL หนุนหลัง — ถ่วงน้ำหนักด้วย "จำนวน × ราคาของวันนั้น"
        raw_in = [d["in_qty_ext"] * (d["unit_in"] or 0.0) for d in days]
        raw_out = [d["out_qty_ext"] * (d["unit_out"] or 0.0) for d in days]
        in_ext, left_in = self._spread_to_days(raw_in, totals["in_value_ext"])
        out_ext, left_out = self._spread_to_days(raw_out, totals["out_value_ext"])

        # ส่วนที่เป็นค่าประมาณของการโอนภายใน — ถ่วงน้ำหนักด้วยจำนวนที่โอนภายใน
        internal_in = [d["in_qty"] - d["in_qty_ext"] for d in days]
        internal_out = [d["out_qty"] - d["out_qty_ext"] for d in days]
        in_imp, left_in_imp = self._spread_to_days(
            internal_in, totals["in_value"] - totals["in_value_ext"]
        )
        out_imp, left_out_imp = self._spread_to_days(
            internal_out, totals["out_value"] - totals["out_value_ext"]
        )

        adj, left_adj = self._spread_to_days(
            [d["svl_adj"] for d in days], totals["adj_value"]
        )

        for index, day in enumerate(days):
            day["in_value"] = in_ext[index] + in_imp[index]
            day["out_value"] = out_ext[index] + out_imp[index]
            day["in_value_ext"] = in_ext[index]
            day["out_value_ext"] = out_ext[index]
            day["adj_value"] = adj[index]
        if days:
            # มูลค่าที่ระบุวันไม่ได้ (เช่น landed cost ที่ไม่ผูกกับ move) ต้องยังอยู่ในสมการ
            # คงเหลือ = ยกมา + รับ − จ่าย + ปรับ จึงไปลงคอลัมน์ปรับมูลค่าของวันสุดท้าย
            days[-1]["adj_value"] += (
                left_adj + left_in + left_in_imp - left_out - left_out_imp
            )

    @api.model
    def _build_day_rows(self, opt, days, totals):
        """เดินยอดคงเหลือสะสม แล้วปัดเศษให้พร้อมแสดง — client ไม่คำนวณอะไรอีก"""
        rounding = self._rounding(opt)
        decimals = self.env["res.company"].browse(opt["company_id"]).currency_id.decimal_places
        show_value = opt["show_value"]
        balance_qty = totals["opening_qty"]
        balance_value = totals["opening_value"] if show_value else 0.0

        rows = []
        for day in days:
            change = day["in_qty"] - day["out_qty"]
            balance_qty += change
            if show_value:
                balance_value += day["in_value"] - day["out_value"] + day["adj_value"]
            rows.append({
                "date": fields.Date.to_string(day["day"]),
                "date_display": self.format_report_date(day["day"], opt["date_format"]),
                "move_count": day["move_count"],
                "in_qty": float_round(day["in_qty"], precision_rounding=rounding),
                "out_qty": float_round(day["out_qty"], precision_rounding=rounding),
                "change": float_round(change, precision_rounding=rounding),
                "balance_qty": float_round(balance_qty, precision_rounding=rounding),
                "in_value": round(day["in_value"], decimals) if show_value else 0.0,
                "out_value": round(day["out_value"], decimals) if show_value else 0.0,
                "adj_value": round(day["adj_value"], decimals) if show_value else 0.0,
                "balance_value": round(balance_value, decimals) if show_value else 0.0,
                # ราคาต่อหน่วยแสดงเฉพาะฝั่งที่วันนั้นมีของจริง ๆ — SVL ของสินค้ามีได้
                # โดยที่โหนดในขอบเขตรายงานไม่มีจำนวน การโชว์ราคาในช่องที่จำนวนว่าง
                # จะอ่านเป็น "ของออกราคา 0" ซึ่งไม่จริง
                "unit_in": round(day["unit_in"], decimals)
                           if show_value and day["in_qty"] and day.get("unit_in") is not None
                           else None,
                "unit_out": round(day["unit_out"], decimals)
                            if show_value and day["out_qty"] and day.get("unit_out") is not None
                            else None,
                "flag": "negative" if (
                    balance_qty < 0
                    and not float_is_zero(balance_qty, precision_rounding=rounding)
                ) else "ok",
            })
        return rows

    @api.model
    def get_product_card(self, options=None, product_id=None):
        """การ์ดสินค้ารายวัน — ช่องทางที่ 4 ของเครื่องยนต์เดียวกัน ไม่ใช่รายงานคนละตัว

        ยอดของสินค้ามาจาก ``_ledger_nodes`` + ``_allocate_value`` ตัวเดิมทั้งดุ้น
        ส่วนแถวรายวันเป็นการ "ซอย" fact ชุดเดิมตามวัน แล้วพิสูจน์ให้เห็นใน ``checks``
        ว่าซอยแล้วยังรวมกลับได้เท่าเดิมทั้งจำนวนและมูลค่า

        :return: dict {options, company, product, totals, days, checks, labels}
        """
        if not self.env.user.has_group("stock.group_stock_user"):
            raise AccessError(_("คุณไม่มีสิทธิ์ดูรายงานคลังสินค้า"))

        opt = self._card_options(options, product_id)
        product_id = opt["product_ids"][0]
        companies = self.env["res.company"].browse(opt["company_ids"])
        company = self.env["res.company"].browse(opt["company_id"])
        currency = company.currency_id

        maps = self._load_maps(opt)
        stats = {
            "interwarehouse_lines": 0, "interwarehouse_qty": 0.0,
            "internal_lines": 0, "truncated_leaves": 0, "detail_rows": 0,
        }
        nodes, denominators = self._ledger_nodes(opt, maps, stats)
        svl = self._read_svl_buckets(opt) if opt["show_value"] else {}
        if opt["show_value"]:
            self._allocate_value(nodes, denominators, svl, opt, stats)

        totals = _zero_measures()
        for node in nodes.values():
            for key in MEASURE_KEYS:
                totals[key] += node[key]

        days = self._day_facts(opt, maps)
        if opt["show_value"]:
            value_moved = any(
                totals[key] for key in ("in_value", "out_value", "adj_value")
            )
            if not days and value_moved:
                # ปรับมูลค่าล้วน ๆ ไม่มีจำนวนเคลื่อนไหวเลย — ต้องมีที่ให้มูลค่าลง
                # ไม่งั้นยอดคงเหลือของการ์ดจะไม่ตรงกับยอดของสินค้า
                blank = _zero_measures()
                blank["day"] = self._to_date(opt["date_to"])
                blank["move_count"] = 0
                days = [blank]
            self._day_values(opt, days, totals, self._read_svl_days(opt))
        else:
            for day in days:
                day.update({
                    "unit_in": None, "unit_out": None,
                    "in_value": 0.0, "out_value": 0.0, "adj_value": 0.0,
                })

        rows = self._build_day_rows(opt, days, totals)
        rounded = self._round_measures(totals, opt, self._rounding(opt))
        rounded["name"] = _("รวมทั้งงวด")
        # ส่วนต่างของทั้งงวด — client ไม่คำนวณตัวเลขเอง แม้แต่การลบสองช่อง
        rounded["change"] = float_round(
            totals["closing_qty"] - totals["opening_qty"],
            precision_rounding=self._rounding(opt),
        )
        checks = self._card_checks(rows, rounded, totals, days, svl, opt, currency,
                                   companies, stats)

        product = self.env["product.product"].browse(product_id).exists()
        labels = self._build_labels(opt, maps)
        labels["title"] = _("รายละเอียดสินค้า")
        return {
            "options": opt,
            "company": {
                "id": company.id,
                "name": company.name,
                "names": " + ".join(companies.mapped("name")),
                "count": len(companies),
                "currency_id": currency.id,
                "currency_symbol": currency.symbol,
                "decimal_places": currency.decimal_places,
                "qty_precision": opt["qty_precision"],
            },
            "warehouses": maps["warehouse_list"],
            "product": {
                "id": product.id,
                "code": product.default_code or "",
                "name": product.name or "",
                "display_name": product.display_name or "",
                "uom_name": product.uom_id.name or "",
                "categ_name": product.categ_id.display_name or "",
                "tracking": product.tracking,
                "avg_cost": self._avg_cost(totals) if opt["show_value"] else None,
            },
            "days": rows,
            "totals": rounded,
            "checks": checks,
            "labels": labels,
        }

    @api.model
    def _card_checks(self, rows, rounded, totals, days, svl, opt, currency, companies, stats):
        """ข้อพิสูจน์ของการ์ด — ซอยรายวันแล้วต้องรวมกลับได้เท่าเดิม"""
        # แถวสังเคราะห์หนึ่งแถวแทน "สินค้าตัวนี้ทั้งตัว" เพื่อใช้ _build_checks ตัวเดิม
        line = dict(rounded)
        line.update({
            "kind": "group", "id": "prod-%s" % opt["product_ids"][0],
            "name": rounded["name"], "counts_to_total": True,
            "flag": self._flag(totals, opt, self._rounding(opt)),
        })
        checks = self._build_checks([line], rounded, svl, opt, currency, companies, stats)

        rounding = self._rounding(opt)
        decimals = currency.decimal_places
        qty_difference = float_round(
            sum(row["in_qty"] - row["out_qty"] for row in rows)
            - (rounded["closing_qty"] - rounded["opening_qty"]),
            precision_rounding=rounding,
        )
        closing = rows[-1]["balance_value"] if rows else rounded["opening_value"]
        value_difference = round(closing - rounded["closing_value"], decimals)
        checks.update({
            "day_count": len(rows),
            "move_count": sum(row["move_count"] for row in rows),
            "qty_difference": qty_difference,
            "qty_reconciled": float_is_zero(qty_difference, precision_rounding=rounding),
            "value_difference": value_difference if opt["show_value"] else 0.0,
            "value_reconciled": not opt["show_value"] or float_is_zero(
                value_difference, precision_rounding=currency.rounding
            ),
        })
        return checks

    @api.model
    def action_day_moves(self, options=None, product_id=None, day=None):
        """รายการเคลื่อนไหวจริงของวันเดียวบนการ์ด

        domain ถูกสร้างที่เซิร์ฟเวอร์จาก ``_base_domain()`` เสมอ เหมือน
        ``action_drill_down`` — ไม่เคยเชื่อ domain ที่ client ส่งมา
        """
        opt = self._card_options(options, product_id)
        target = self._to_date(day)
        if not target:
            raise UserError(_("ไม่พบวันที่ที่ต้องการดูรายการเคลื่อนไหว"))
        start, end = self._period_bounds(target, target, opt["tz"])
        domain = self._base_domain(opt) + [
            ("date", ">=", fields.Datetime.to_string(start)),
            ("date", "<=", fields.Datetime.to_string(end)),
        ]
        return {
            "type": "ir.actions.act_window",
            "name": _("รายการเคลื่อนไหว — %s") % self.format_report_date(
                target, opt["date_format"]
            ),
            "res_model": "stock.move.line",
            "view_mode": "list,form",
            # OWL doAction ไม่ผ่าน clean_action จึงต้องส่ง views มาเองให้ครบ
            "views": [(False, "list"), (False, "form")],
            "domain": domain,
            "context": {"create": False},
        }

    # ==================================================================
    # Drill-down
    # ==================================================================
    @api.model
    def _parse_line_id(self, line_id):
        parts = {}
        for segment in (line_id or "").split("/"):
            if "-" not in segment:
                continue
            prefix, _sep, raw = segment.rpartition("-")
            try:
                parts[prefix] = int(raw)
            except ValueError:
                continue
        return parts

    @api.model
    def _drill_moves(self, parts, opt, maps):
        domain = self._base_domain(opt) + [
            ("date", ">=", opt["datetime_from"]),
            ("date", "<=", opt["datetime_to"]),
        ]
        if parts.get("co"):
            domain.append(("company_id", "=", parts["co"]))
        if parts.get("prod"):
            domain.append(("product_id", "=", parts["prod"]))
        if parts.get("categ"):
            domain.append(("product_id.categ_id", "child_of", parts["categ"]))
        if "lot" in parts:
            domain.append(("lot_id", "=", parts["lot"] or False))
        locs = self._drill_location_ids(parts, opt, maps)
        if locs is not None:
            domain += ["|", ("location_id", "in", locs), ("location_dest_id", "in", locs)]
        return {
            "type": "ir.actions.act_window",
            "name": _("รายการเคลื่อนไหว — %s") % self._drill_title(parts, maps),
            "res_model": "stock.move.line",
            "view_mode": "list,form",
            # OWL doAction ไม่ผ่าน clean_action จึงต้องส่ง views มาเองให้ครบ
            "views": [(False, "list"), (False, "form")],
            "domain": domain,
            "context": {"create": False, "search_default_groupby_product_id": 1},
        }

    @api.model
    def _drill_valuation(self, parts, opt):
        domain = self._svl_period_domain(opt)
        if parts.get("co"):
            domain.append(("company_id", "=", parts["co"]))
        if parts.get("prod"):
            domain.append(("product_id", "=", parts["prod"]))
        if parts.get("categ"):
            domain.append(("product_id.categ_id", "child_of", parts["categ"]))
        return {
            "type": "ir.actions.act_window",
            # ชื่อบอกตรง ๆ ว่าเป็นระดับบริษัท เพราะ SVL ไม่มีมิติคลัง/ที่เก็บ/ล็อต
            "name": _("มูลค่า (ระดับบริษัท) — %s") % self._drill_title(parts, {}),
            "res_model": "stock.valuation.layer",
            "view_mode": "list,form",
            "views": [(False, "list"), (False, "form")],
            "domain": domain,
            "context": {"create": False},
        }

    @api.model
    def _drill_document(self, move_line_id):
        line = self.env["stock.move.line"].browse(move_line_id).exists()
        if line.picking_id:
            return {
                "type": "ir.actions.act_window",
                "name": line.picking_id.name,
                "res_model": "stock.picking",
                "res_id": line.picking_id.id,
                "view_mode": "form",
                "views": [(False, "form")],
            }
        return {
            "type": "ir.actions.act_window",
            "name": line.reference or _("รายการเคลื่อนไหว"),
            "res_model": "stock.move.line",
            "view_mode": "list,form",
            "views": [(False, "list"), (False, "form")],
            "domain": [("id", "=", move_line_id)],
            "context": {"create": False},
        }

    @api.model
    def _drill_location_ids(self, parts, opt, maps):
        if parts.get("loc"):
            return self._scoped("stock.location", opt).sudo().search(
                [("id", "child_of", parts["loc"])]
            ).ids
        if parts.get("wh"):
            return [
                loc_id for loc_id, info in (maps.get("location") or {}).items()
                if info["warehouse_id"] == parts["wh"] and info["on_hand"]
            ]
        return None

    @api.model
    def _drill_title(self, parts, maps):
        if parts.get("prod"):
            product = self.env["product.product"].browse(parts["prod"]).exists()
            if product:
                return product.display_name
        if parts.get("wh"):
            warehouse = self.env["stock.warehouse"].browse(parts["wh"]).exists()
            if warehouse:
                return warehouse.display_name
        return _("สต๊อกการ์ด")

    # ==================================================================
    # Column spec (ใช้ร่วมกันระหว่าง PDF และ Excel)
    # ==================================================================
    @api.model
    def report_columns(self, report_data):
        """นิยามคอลัมน์ชุดเดียวของไฟล์ที่ส่งออก

        PDF กับ Excel ต้องอ่านคู่กันได้โดยไม่งง จึงใช้สเปกตัวเดียวกัน — ข้อมูลไม่เคย
        ถูกคำนวณซ้ำ มีแต่การจัดวางที่แชร์กัน
        """
        opt = report_data["options"]
        show_value = opt["show_value"]
        has_detail = any(line["kind"] in ("move", "more") for line in report_data["lines"])

        columns = [
            {"group": "", "label": "รหัส / วันที่", "key": "code", "type": "text", "width": "10%"},
            {"group": "", "label": "รายการ", "key": "name", "type": "name", "width": "24%"},
            {"group": "", "label": "หน่วย", "key": "uom_name", "type": "uom", "width": "6%"},
        ]
        for group, qty_key, value_key in (
            ("ยอดยกมา", "opening_qty", "opening_value"),
            ("รับ", "in_qty", "in_value"),
            ("จ่าย", "out_qty", "out_value"),
        ):
            columns.append({"group": group, "label": "จำนวน", "key": qty_key, "type": "qty"})
            if show_value:
                columns.append({"group": group, "label": "มูลค่า", "key": value_key, "type": "money"})
        if show_value:
            columns.append(
                {"group": "", "label": "ปรับมูลค่า", "key": "adj_value", "type": "money"}
            )
        columns.append({"group": "คงเหลือ", "label": "จำนวน", "key": "closing_qty", "type": "qty"})
        if show_value:
            columns.append(
                {"group": "คงเหลือ", "label": "มูลค่า", "key": "closing_value", "type": "money"}
            )
        if has_detail:
            columns.append(
                {"group": "คงเหลือสะสม", "label": "จำนวน", "key": "balance_qty", "type": "qty"}
            )
            if show_value:
                columns.append(
                    {"group": "คงเหลือสะสม", "label": "มูลค่า", "key": "balance_value",
                     "type": "money"}
                )

        # จับคู่หัวคอลัมน์สองชั้น: colspan ของหัวกลุ่ม และตำแหน่งที่ต้อง rowspan
        index = 0
        while index < len(columns):
            group = columns[index]["group"]
            span = 1
            if group:
                while index + span < len(columns) and columns[index + span]["group"] == group:
                    span += 1
            columns[index]["group_span"] = span if group else 0
            columns[index]["group_first"] = True
            for offset in range(1, span):
                columns[index + offset]["group_span"] = 0
                columns[index + offset]["group_first"] = False
            index += span
        return columns

    # ==================================================================
    # Checks / labels
    # ==================================================================
    @api.model
    def _build_checks(self, lines, totals, svl, opt, currency, companies, stats):
        """สิ่งที่ผู้ใช้ต้องรู้ก่อนเชื่อตัวเลข — แบนเนอร์บนจอ, กล่องใน PDF, ชีตใน Excel"""
        decimals = currency.decimal_places
        svl_period = sum(value for value, _count in (svl.get("control") or {}).values())
        report_external = sum(
            line["in_value_ext"] - line["out_value_ext"] + line["adj_value"]
            for line in lines if line.get("counts_to_total")
        )
        difference = round(report_external - svl_period, decimals)
        # SVL ไม่มีมิติคลัง/ที่เก็บ รายงานที่กรองคลังจึงเทียบกับยอด SVL ทั้งบริษัทไม่ได้
        scope_limited = bool(opt["warehouse_ids"] or opt["location_ids"])

        negative = [
            {"id": line["id"], "name": line["name"], "qty": line["closing_qty"]}
            for line in lines
            if line["kind"] == "group" and line.get("flag") == "negative"
        ][:20]
        other_currency = companies.filtered(lambda c: c.currency_id.id != currency.id)
        return {
            "show_value": opt["show_value"],
            "value_hidden_reason": opt["value_hidden_reason"],
            "value_mode": opt["value_mode"],
            "value_date_basis": opt["value_date_basis"],
            "svl_period_value": round(svl_period, decimals),
            "report_period_value": round(report_external, decimals),
            "svl_difference": difference,
            "svl_scope_limited": scope_limited,
            "svl_reconciled": opt["show_value"] and not scope_limited and float_is_zero(
                difference, precision_rounding=currency.rounding
            ),
            "imputed_internal": {
                "line_count": stats.get("internal_lines", 0),
                "value": round(stats.get("imputed_abs", 0.0), decimals),
                "net": round(stats.get("imputed_net", 0.0), decimals),
            },
            "interwarehouse": {
                "line_count": stats.get("interwarehouse_lines", 0),
                "qty": float_round(
                    stats.get("interwarehouse_qty", 0.0),
                    precision_rounding=self._rounding(opt),
                ),
            },
            "negative_balances": negative,
            "mixed_currency": [
                {"id": c.id, "name": c.name, "currency": c.currency_id.name}
                for c in other_currency
            ],
            # ปิดการปรับปรุงยอดหรือของเสียทิ้ง = สมการ คงเหลือ = ยกมา + รับ − จ่าย ไม่จริงอีกต่อไป
            "balance_broken_by_filter": not (
                opt["include_inventory"] and opt["include_scrap"]
            ),
            "detail_downgraded": opt["detail_downgraded"],
            "truncated_leaves": stats.get("truncated_leaves", 0),
            "detail_rows": stats.get("detail_rows", 0),
            "group_count": sum(1 for line in lines if line["kind"] == "group"),
            "opening_skipped": opt["opening_basis"] == "none",
        }

    @api.model
    def _build_labels(self, opt, maps):
        levels = " → ".join(LEVEL_LABEL[lv] for lv in opt["levels"])
        warehouses = ", ".join(
            maps["warehouse"].get(w, {}).get("name", str(w)) for w in opt["warehouse_ids"]
        )
        excluded = []
        if not opt["include_inventory"]:
            excluded.append(_("ไม่รวมการปรับปรุงยอด"))
        if not opt["include_scrap"]:
            excluded.append(_("ไม่รวมของเสีย"))
        if opt["include_consignment"]:
            excluded.append(_("รวมสินค้าฝากขาย"))
        return {
            "title": _("สต๊อกการ์ด (Stock Card)"),
            "period": _("ตั้งแต่ %s ถึง %s") % (
                self.format_report_date(opt["date_from"], opt["date_format"]),
                self.format_report_date(opt["date_to"], opt["date_format"]),
            ),
            "companies": " + ".join(
                maps["company"].get(c, "") for c in opt["company_ids"]
            ),
            "company_mode": _("รวมทุกบริษัท") if opt["company_mode"] == "consolidated"
                            else _("แยกตามบริษัท"),
            "group_mode": levels,
            "levels": levels,
            "warehouses": warehouses or _("ทุกคลัง"),
            "value_mode": _("ประมาณมูลค่าการโอนภายใน") if opt["value_mode"] == "imputed"
                          else _("เฉพาะมูลค่าที่มี SVL"),
            "value_date_basis": _("วันที่เคลื่อนไหว") if opt["value_date_basis"] == "move"
                                else _("วันที่บันทึกมูลค่า"),
            "detail_mode": {
                "none": _("ไม่แสดงรายการเคลื่อนไหว"),
                "unfolded": _("แสดงรายการเคลื่อนไหวเฉพาะกลุ่มที่กาง"),
                "all": _("แสดงรายการเคลื่อนไหวทั้งหมด"),
            }[opt["detail_mode"]],
            "opening_basis": _("ยอดยกมาจากทุกรายการก่อนวันเริ่มงวด")
                             if opt["opening_basis"] == "moves" else _("ไม่คำนวณยอดยกมา"),
            "filters": " / ".join(excluded) if excluded else _("ไม่มีเงื่อนไขพิเศษ"),
            "timezone": opt["tz"],
        }
