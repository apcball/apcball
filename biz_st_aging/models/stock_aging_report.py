# -*- coding: utf-8 -*-
"""เครื่องยนต์คำนวณอายุสินค้าคงเหลือ — แหล่งความจริงเดียวของทั้งหน้าจอ, PDF และ Excel

หน้าจอ OWL / QWeb PDF / xlsxwriter ต้องเรียก ``get_report_data()`` ตัวนี้เท่านั้น
ห้ามมีเส้นทางคำนวณเส้นที่สอง ไม่งั้นตัวเลขบนจอกับตัวเลขในไฟล์ที่ส่งผู้ตรวจสอบ
จะเพี้ยนจากกันโดยไม่มีใครรู้

สถาปัตยกรรมโดยย่อ (ลอกหลักการจาก biz_st_stock_card แต่ไม่ depend กัน)
----------------------------------------------------------------------

1. ``_read_group`` บน ``stock.move.line`` (done) ให้ผลรวมจำนวนต่อ
   (บริษัท, สินค้า, ที่มา, ที่ไป[, ล็อต]) สองช่วง: ก่อนช่วงใช้งาน / ในช่วงใช้งาน
2. ``_emit_fact_row`` แปลงแต่ละก้อนเป็น fact ตามกฎ: ที่มาเป็นของคงคลัง → OUT ที่โหนด
   ต้นทาง, ที่ไปเป็นของคงคลัง → IN ที่โหนดปลายทาง, โหนดเดียวกัน → ไม่ปล่อย
   ได้ ``closing_qty`` = **คงเหลือ ณ วันที่** ต่อโหนด และวันจ่ายล่าสุด
3. ``_walk_layers`` คิวรีเดียว (SQL window function บน FROM/WHERE ของ ``_where_calc``) หายอด
   สะสมของ IN fact ระดับวันต่อโหนดจากใหม่ไปเก่า ส่งกลับเฉพาะชั้นที่ยังไม่พอคงเหลือ แล้วกิน
   ใน Python (FIFO: ของที่เหลือคือของที่รับเข้าล่าสุด) → จำนวนต่อช่วงอายุ
   (``_walk_layers_windowed`` = เวอร์ชัน ORM รายหน้าต่างเดิม ใช้เทียบผลในเทสเท่านั้น)
4. มูลค่าจาก ``stock.valuation.layer`` ณ วันที่ (ระดับบริษัท×สินค้า) กระจายลงโหนดตาม
   สัดส่วนจำนวน แล้วซอยลงช่วงอายุตามสัดส่วนจำนวนของช่วง — ผลรวมกระทบ SVL เป๊ะ
5. ``_build_tree`` pivot โหนดตามลำดับระดับที่ผู้ใช้เลือก — สลับแกน คลัง↔สินค้า
   เป็นแค่การสลับลำดับ key ไม่ใช่โค้ดคนละเส้น
6. ข้อ 1-4 อยู่ใน ``_computed_nodes`` และถูกแคชต่อ worker (คีย์รวมลายนิ้วมือข้อมูล) ข้อ 5
   ทำใหม่ทุกครั้ง — กาง/หุบแถวจึงไม่แตะ DB
"""

import hashlib
import json
import logging
import re
import time as time_mod
from datetime import date, datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL, float_is_zero, float_round
from odoo.tools.lru import LRU

_logger = logging.getLogger(__name__)

# แคชผลคำนวณ "ระดับโหนด" ต่อ worker — กาง/หุบแถว เปลี่ยนรูปแบบวันที่ หรือสลับ "แสดงสินค้า"
# ไม่ต้องกวาด stock.move.line ใหม่ คีย์ = (db, uid, core options, ลายนิ้วมือข้อมูล)
# ลายนิ้วมือ (count/max id/max write_date ของ move line + SVL) ทำให้แคชหมดอายุเองทันทีที่
# มีรายการใหม่หรือแก้ไข ส่วน TTL เป็นแค่เพดานกันแผนที่ชื่อสินค้า/ที่เก็บค้างนานเกิน
NODES_CACHE = LRU(16)
NODES_CACHE_TTL = 600
# คีย์ options ที่กระทบแค่การแสดงผล (ทรี/ป้าย) ไม่กระทบตัวเลขระดับโหนด
RENDER_ONLY_KEYS = frozenset((
    "unfolded", "unfold_level", "display_product", "date_format", "value_hidden_reason",
    "max_lines",
))

BUCKET_COUNT = 6
BUCKET_QTY_KEYS = tuple("b%d_qty" % i for i in range(BUCKET_COUNT))
BUCKET_VAL_KEYS = tuple("b%d_value" % i for i in range(BUCKET_COUNT))
# จำนวนจากบัญชีคุม (ช่วงใช้งาน) + จำนวนที่จัดชั้นอายุแล้ว
QTY_KEYS = (
    "opening_qty", "in_qty", "out_qty", "closing_qty", "usage_qty",
    "bucketed_qty", "unlayered_qty",
) + BUCKET_QTY_KEYS
VAL_KEYS = ("closing_value",) + BUCKET_VAL_KEYS
# age_qty_sum = Σ(อายุ × จำนวน) บวกกันได้ทุกระดับ → อายุเฉลี่ยของแถวใด ๆ = age_qty_sum / bucketed_qty
ADDITIVE_KEYS = QTY_KEYS + VAL_KEYS + ("age_qty_sum",)
# วันที่ที่รวมแบบ max/min ไม่ใช่บวก
DATE_KEYS = ("last_out", "newest_in", "oldest_in")

STATUS_LABEL = {
    "normal": "ปกติ",
    "slow": "ช้า",
    "non_moving": "ไม่เคลื่อนไหว",
    "obsolete": "ตาย",
}
RISK_STATUSES = ("non_moving", "obsolete")

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

# ตำแหน่งคงที่ในคีย์ของโหนด — (company, warehouse, product, location, lot)
K_COMPANY, K_WH, K_PRODUCT, K_LOC, K_LOT = range(5)

_LINE_ID_RE = re.compile(r"^[a-z]+-\d+(?:/[a-z]+-\d+)*$")

AGE_BASIS = ("node_in",)
COST_BASIS = ("average",)


def _zero_measures():
    node = dict.fromkeys(ADDITIVE_KEYS, 0.0)
    for key in DATE_KEYS:
        node[key] = None
    return node


def _merge_dates(target, source):
    for key in ("last_out", "newest_in"):
        if source.get(key) and (not target.get(key) or source[key] > target[key]):
            target[key] = source[key]
    if source.get("oldest_in") and (
        not target.get("oldest_in") or source["oldest_in"] < target["oldest_in"]
    ):
        target["oldest_in"] = source["oldest_in"]


class StockAgingReport(models.AbstractModel):
    _name = "biz.stock.aging.report"
    _description = "Stock Aging Engine (อายุสินค้าคงเหลือ)"

    # ==================================================================
    # Public API
    # ==================================================================
    @api.model
    def get_filter_options(self, options=None):
        """ตัวเลือกตัวกรอง (คลัง/หมวด/บริษัท/ระดับ) โดยไม่คำนวณตัวรายงาน

        ใช้เติมแถบตัวกรองตอนเปิดหน้าจอครั้งแรก — เบาเพราะอ่านแค่มิติ (``_load_maps``)
        ไม่แตะ ``stock.move.line``/SVL เลย ผู้ใช้เลือกตัวกรองแล้วกด "ค้นหา" ค่อยเรียก
        ``get_report_data`` ของจริง กันไม่ให้บริษัทที่ข้อมูลเยอะเปิดจอแล้วเจอ Invalid
        Operation (เกิน ``max_lines``) ทันทีโดยยังไม่ทันได้กรองอะไรเลย
        """
        if not self.env.user.has_group("biz_st_aging.group_stock_aging_user"):
            raise AccessError(_("คุณไม่มีสิทธิ์ดูรายงานคลังสินค้า"))
        opt = self._normalize_options(options)
        maps = self._load_maps(opt)
        return {
            "options": opt,
            "allowed_companies": [
                {"id": c.id, "name": c.name} for c in self.env.user.company_ids
            ],
            "warehouses": maps["warehouse_list"],
            "categories": maps["categ_list"],
            "levels": [{"type": lv, "label": LEVEL_LABEL[lv]} for lv in opt["levels"]],
        }

    @api.model
    def get_report_data(self, options=None):
        """คืนข้อมูลอายุสินค้าคงเหลือทั้งชุดสำหรับ options ที่ให้มา

        :return: dict {options, company, companies, allowed_companies, warehouses,
                       categories, levels, buckets, config, columns, lines, totals,
                       kpis, checks, labels}
        """
        if not self.env.user.has_group("biz_st_aging.group_stock_aging_user"):
            raise AccessError(_("คุณไม่มีสิทธิ์ดูรายงานคลังสินค้า"))

        opt = self._normalize_options(options)
        companies = self.env["res.company"].browse(opt["company_ids"])
        company = self.env["res.company"].browse(opt["company_id"])
        currency = company.currency_id

        computed = self._computed_nodes(opt, nocache=bool((options or {}).get("nocache")))
        nodes, maps, svl, stats = (
            computed["nodes"], computed["maps"], computed["svl"], computed["stats"]
        )

        lines, totals, product_risk = self._build_tree(nodes, opt, maps)
        if len(lines) > opt["max_lines"]:
            # ตัวเลขถูกต้องอยู่แล้ว (แคชไว้) แต่ทรีที่กางออกใหญ่เกินจะวาด/พิมพ์ไหว — ให้ผู้ใช้หุบหรือกรอง
            raise UserError(_(
                "รายงานนี้มี %s แถวที่จะแสดง ซึ่งเกินขีดจำกัด %s แถว\n\n"
                "กด 'หุบทั้งหมด' แล้วกางเฉพาะกลุ่มที่ต้องการ กรองคลัง หมวดสินค้า หรือสินค้าให้แคบลง "
                "หรือปิดระดับ 'ที่เก็บย่อย' / 'ล็อต-ซีเรียล' (ไฟล์ Excel รับได้มากกว่าหน้าจอ)"
            ) % (len(lines), opt["max_lines"]))
        kpis = self._build_kpis(totals, product_risk, opt, currency)
        checks = self._build_checks(lines, totals, svl, opt, currency, companies, stats)
        checks["from_cache"] = computed["from_cache"]
        data = {
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
            "companies": [{"id": c.id, "name": c.name} for c in companies],
            "allowed_companies": [
                {"id": c.id, "name": c.name} for c in self.env.user.company_ids
            ],
            "warehouses": maps["warehouse_list"],
            "categories": maps["categ_list"],
            "levels": [{"type": lv, "label": LEVEL_LABEL[lv]} for lv in opt["levels"]],
            "buckets": opt["buckets"],
            "config": {
                "bucket_edges": opt["bucket_edges"],
                "usage_months": opt["usage_months"],
                "slow_mos_months": opt["slow_mos_months"],
                "non_moving_days": opt["non_moving_days"],
                "obsolete_days": opt["obsolete_days"],
                "company_name": company.name,
            },
            "status_labels": STATUS_LABEL,
            "lines": lines,
            "totals": totals,
            "kpis": kpis,
            "checks": checks,
            "labels": self._build_labels(opt, maps),
        }
        data["columns"] = self.report_columns(data)
        return data

    # ==================================================================
    # Node-level cache
    # ==================================================================
    @api.model
    def _computed_nodes(self, opt, nocache=False):
        """ทุกอย่างที่ต้องกวาด stock.move.line / SVL — คืน {nodes, maps, svl, stats, from_cache}

        ผลลัพธ์ถูกแคชต่อ worker; ``_build_tree`` และ ``_build_labels`` อ่านอย่างเดียว ห้ามแก้
        ``nodes``/``maps`` หลังจากนี้ ไม่งั้นการเรียกครั้งถัดไปได้ตัวเลขเพี้ยน
        """
        key = self._nodes_cache_key(opt)
        now = time_mod.time()
        if not nocache:
            hit = NODES_CACHE.get(key)
            if hit is not None and now - hit["at"] < NODES_CACHE_TTL:
                return dict(hit, from_cache=True)

        maps = self._load_maps(opt)
        stats = {"layer_rows": 0, "walk_windows_run": 0, "unbucketed_value": 0.0}
        nodes, denominators = self._ledger_nodes(opt, maps, stats)
        self._read_usage(opt, maps, nodes)
        self._walk_layers(opt, maps, nodes, stats)

        svl = {}
        if opt["show_value"]:
            svl = self._read_svl_closing(opt)
            self._allocate_value(nodes, denominators, svl, opt)
            # การกระจายมูลค่าอาจสร้างโหนด "ไม่ระบุคลัง" ของสินค้าที่ไม่มีจำนวนเลย
            self._fill_product_map(opt, maps, sorted({k[K_PRODUCT] for k in nodes}))
            self._spread_bucket_values(nodes, opt, stats)

        entry = {
            "at": now, "nodes": nodes, "maps": maps, "svl": svl, "stats": stats,
            "from_cache": False,
        }
        NODES_CACHE[key] = entry
        return entry

    @api.model
    def _nodes_cache_key(self, opt):
        core = {k: v for k, v in opt.items() if k not in RENDER_ONLY_KEYS}
        digest = hashlib.sha1(
            json.dumps(core, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return (self.env.cr.dbname, self.env.uid, digest, self._data_fingerprint(opt))

    @api.model
    def _data_fingerprint(self, opt):
        """ลายนิ้วมือของข้อมูลต้นทางในขอบเขตบริษัท — เปลี่ยนทันทีที่มี move line/SVL ใหม่หรือถูกแก้

        เป็นแค่ตัวเลขไว้ทำคีย์แคช ไม่ได้ส่งให้ผู้ใช้ จึงอ่านตรงจาก SQL ได้ (ไม่ผ่าน ir.rule)
        ราคาถูกกว่าการคำนวณใหม่หลายร้อยเท่า (index company_id + สแกน write_date ของบริษัทเดียว)
        """
        self.env["stock.move.line"].flush_model()
        self.env["stock.valuation.layer"].flush_model()
        companies = tuple(opt["company_ids"])
        cr = self.env.cr
        cr.execute(
            "SELECT COUNT(*), MAX(id), MAX(write_date) FROM stock_move_line "
            "WHERE state = 'done' AND company_id IN %s",
            (companies,),
        )
        moves = cr.fetchone()
        cr.execute(
            "SELECT COUNT(*), MAX(id), MAX(write_date), MAX(create_date) "
            "FROM stock_valuation_layer WHERE company_id IN %s",
            (companies,),
        )
        layers = cr.fetchone()
        return tuple(moves) + tuple(layers)

    @api.model
    def _clear_nodes_cache(self):
        NODES_CACHE.clear()

    @api.model
    def action_drill_down(self, line_id, options=None):
        """แถวรายงาน → รายการเคลื่อนไหวดิบที่ประกอบเป็นยอดคงเหลือนั้น

        domain สร้างใหม่จาก ``_base_domain()`` เสมอ ไม่เชื่อสิ่งที่ client ส่งมา
        """
        opt = self._normalize_options(options)
        parts = self._parse_line_id(line_id)
        maps = self._load_maps(opt)
        return self._drill_moves(parts, opt, maps)

    @api.model
    def action_open_product(self, line_id, options=None):
        """กดชื่อสินค้า — ถ้ามี biz_st_stock_card ให้เปิดการ์ดสินค้ารายวันของมัน
        (ส่งเฉพาะคีย์ที่ stock card รู้จัก) ไม่งั้นเปิดรายการเคลื่อนไหว
        """
        opt = self._normalize_options(options)
        parts = self._parse_line_id(line_id)
        product_id = parts.get("prod")
        if product_id and self._has_stock_card():
            product = self.env["product.product"].browse(product_id).exists()
            return {
                "type": "ir.actions.client",
                "tag": "biz_st_stock_card.product_card",
                "name": _("รายละเอียดสินค้า: %s") % (product.display_name if product else ""),
                "context": {
                    "sc_options": {
                        "company_ids": opt["company_ids"],
                        "company_mode": opt["company_mode"],
                        "date_from": opt["date_from"],
                        "date_to": opt["date_to"],
                        "tz": opt["tz"],
                        "date_format": opt["date_format"],
                        "warehouse_ids": opt["warehouse_ids"],
                        "location_ids": opt["location_ids"],
                        "include_consignment": opt["include_consignment"],
                        "group_mode": opt["group_mode"],
                    },
                    "sc_product_id": product_id,
                },
            }
        maps = self._load_maps(opt)
        return self._drill_moves(parts, opt, maps)

    @api.model
    def action_open_config(self, options=None):
        """ปุ่ม "ตั้งค่า Aging" — ฟอร์มตั้งค่าของบริษัทหลักของรายงาน (สร้างให้ถ้ายังไม่มี)"""
        opt = self._normalize_options(options)
        config = self.env["biz.stock.aging.config"].get_for_company(opt["company_id"])
        return {
            "type": "ir.actions.act_window",
            "name": _("ตั้งค่าอายุสินค้าคงเหลือ"),
            "res_model": "biz.stock.aging.config",
            "res_id": config.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
        }

    @api.model
    def _has_stock_card(self):
        return "biz.stock.card.report" in self.env.registry

    @api.model
    def format_report_date(self, value, date_format="be"):
        """dd/mm/yyyy โดยปีเป็น พ.ศ. (be) หรือ ค.ศ. (ce)"""
        if not value:
            return ""
        value = self._to_date(value)
        year = value.year + 543 if date_format == "be" else value.year
        return "%02d/%02d/%d" % (value.day, value.month, year)

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
        config = self.env["biz.stock.aging.config"].get_for_company(main_id).to_options()

        today = fields.Date.context_today(self)
        date_to = self._to_date(opt.get("date_to")) or today
        usage_months = config["usage_months"]
        # ช่วง N เดือนที่ "จบ" ที่ ณ วันที่ — (ณ วันที่ + 1) − N เดือน: 30 มิ.ย. ย้อน 6 เดือน = 1 ม.ค.
        date_from = date_to + timedelta(days=1) - relativedelta(months=usage_months)

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
            "date_to": fields.Date.to_string(date_to),
            "date_from": fields.Date.to_string(date_from),
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
            "warehouse_ids": self._clean_ids(opt.get("warehouse_ids")),
            "location_ids": self._clean_ids(opt.get("location_ids")),
            "product_ids": self._clean_ids(opt.get("product_ids")),
            "categ_ids": self._clean_ids(opt.get("categ_ids")),
            "lot_ids": self._clean_ids(opt.get("lot_ids")),
            "product_search": (opt.get("product_search") or "").strip()[:100]
                              if isinstance(opt.get("product_search"), str) else "",
            "include_consignment": bool(opt.get("include_consignment", False)),
            "show_value": show_value,
            "age_basis": opt.get("age_basis") or "node_in",
            "cost_basis": opt.get("cost_basis") or "average",
            "display_product": opt.get("display_product") or "on_hand",
            "max_groups": int(opt.get("max_groups") or 20000),
            "max_layer_rows": int(opt.get("max_layer_rows") or 200000),
            # เพดานแถวที่ "แสดง" (หลังกาง) — จอ 5,000; PDF/Excel ตั้งค่าเองใน generator ของตัวเอง
            "max_lines": int(opt.get("max_lines") or 5000),
            # จาก config ของบริษัทหลัก — echo ให้ client ใช้ทำหัวตาราง/KPI ไม่ต้อง hard-code
            "usage_months": usage_months,
            "bucket_edges": config["bucket_edges"],
            "slow_mos_months": config["slow_mos_months"],
            "non_moving_days": config["non_moving_days"],
            "obsolete_days": config["obsolete_days"],
        }
        if normalized["company_mode"] not in ("consolidated", "split"):
            normalized["company_mode"] = "consolidated"
        if normalized["date_format"] not in ("be", "ce"):
            normalized["date_format"] = "be"
        if normalized["group_mode"] not in ("wh_product", "product_wh"):
            normalized["group_mode"] = "wh_product"
        if normalized["age_basis"] not in AGE_BASIS:
            normalized["age_basis"] = "node_in"
        if normalized["cost_basis"] not in COST_BASIS:
            normalized["cost_basis"] = "average"
        if normalized["display_product"] not in ("on_hand", "all"):
            normalized["display_product"] = "on_hand"
        normalized["unfold_level"] = max(0, min(7, normalized["unfold_level"]))
        normalized["max_groups"] = max(1000, min(200000, normalized["max_groups"]))
        normalized["max_layer_rows"] = max(1000, min(2000000, normalized["max_layer_rows"]))
        normalized["max_lines"] = max(10, min(200000, normalized["max_lines"]))

        normalized["value_hidden_reason"] = (
            "no_accounting_group"
            if opt.get("show_value", True) and not show_value
            else False
        )
        normalized["levels"] = self._group_levels(normalized)
        normalized["buckets"] = self._bucket_specs(normalized["bucket_edges"])
        normalized["qty_precision"] = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        return normalized

    @api.model
    def _bucket_specs(self, edges):
        """[{key, label, lo, hi}] — hi = None คือช่วงสุดท้าย (ไม่มีขอบบน)"""
        specs = []
        lo = 0
        for index, edge in enumerate(edges):
            specs.append({
                "key": "b%d" % index,
                "label": "%d-%d" % (lo, edge),
                "lo": lo, "hi": edge,
            })
            lo = edge + 1
        specs.append({"key": "b5", "label": "> %d" % edges[-1], "lo": lo, "hi": None})
        return specs

    @api.model
    def _resolve_company_ids(self, opt):
        """บริษัทที่รายงานจะครอบคลุม — ตรวจสิทธิ์กับ ``user.company_ids`` ไม่ใช่ ``env.companies``"""
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
        """ขอบช่วงเป็นเวลาท้องถิ่นของผู้ใช้ แปลงเป็น naive UTC — upper bound เป็น exclusive
        เที่ยงคืนของวันถัดไป (``[date_from, date_to+1)``) ให้ตรงกับ
        ``stock_fifo_valuation_report``'s ``_bangkok_day_range_to_utc`` แทนที่จะปิดที่
        23:59:59 inclusive แบบเดิม (ผลต่าง 1 วินาทีทำให้สอง report เห็นข้อมูลไม่ตรงกันที่
        ขอบวัน) — ทุกจุดเรียกที่ใช้ ``datetime_to``/``dt_to``/``hi_dt`` เป็น upper bound
        ต้องเทียบด้วย ``<`` ไม่ใช่ ``<=``
        """
        zone = pytz.timezone(tz)
        start = zone.localize(datetime.combine(date_from, time.min))
        end = zone.localize(datetime.combine(date_to + timedelta(days=1), time.min))
        return (
            start.astimezone(pytz.UTC).replace(tzinfo=None),
            end.astimezone(pytz.UTC).replace(tzinfo=None),
        )

    @api.model
    def _group_levels(self, opt):
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
        """ผู้ใช้ที่มีสิทธิ์บัญชี หรือ stock manager (ACL ของ SVL ให้อยู่แล้ว) — override จุดเดียวถ้าต้องการนโยบายอื่น"""
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
        if isinstance(value, datetime):
            return value.date()
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
        """ทุกคิวรีต้องผ่านตัวนี้ — ir.rule ของ stock อิง ``allowed_company_ids`` ใน context"""
        return self.env[model].with_context(
            allowed_company_ids=opt["company_ids"], active_test=False
        )

    @api.model
    def _base_domain(self, opt):
        """เงื่อนไขร่วมของทุกคิวรีบน stock.move.line (ยังไม่รวมวันที่)

        ตัวกรองคลัง/ที่เก็บ **ไม่อยู่ในนี้โดยตั้งใจ** — ถูกใช้ตอนปล่อย fact แทน
        การปรับปรุงยอดและของเสีย **รวมเสมอ** ไม่งั้นยอดคงเหลือไม่ตรงกับของจริง
        """
        domain = [
            ("company_id", "in", opt["company_ids"]),
            ("state", "=", "done"),
            ("product_id.type", "=", "product"),
            ("quantity_product_uom", "!=", 0),
            "|", ("picked", "=", True), ("move_id.is_inventory", "=", True),
        ]
        if not opt["include_consignment"]:
            domain.append(("owner_id", "=", False))
        domain += self._product_domain(opt, "product_id")
        if opt["lot_ids"]:
            domain.append(("lot_id", "in", opt["lot_ids"]))
        return domain

    @api.model
    def _product_domain(self, opt, field):
        domain = []
        if opt["product_ids"]:
            domain.append((field, "in", opt["product_ids"]))
        if opt["categ_ids"]:
            domain.append((field + ".categ_id", "child_of", opt["categ_ids"]))
        if opt["product_search"]:
            # many2one + ilike = name_search ของ product.product (รหัส/ชื่อ/บาร์โค้ด)
            domain.append((field, "ilike", opt["product_search"]))
        return domain

    @api.model
    def _svl_model(self, opt):
        """stock.valuation.layer ที่อ่านได้จริง — sudo เฉพาะผู้ใช้บัญชีที่ไม่ใช่ stock manager
        (ปลอดภัยเพราะเรียกก็ต่อเมื่อผ่าน ``_can_see_value()`` และ ``_resolve_company_ids()`` แล้ว)
        """
        model = self._scoped("stock.valuation.layer", opt)
        if not self.env.user.has_group("stock.group_stock_manager"):
            model = model.sudo()
        return model

    @api.model
    def _svl_domain(self, opt):
        return [("company_id", "in", opt["company_ids"])] + self._product_domain(opt, "product_id")

    @api.model
    def _svl_date_domain(self, opt, operator, bound):
        """กรอง SVL ด้วย ``accounting_date`` (fallback ``create_date`` เมื่อไม่มี) —
        field เดียวกับที่ ``stock_fifo_valuation_report`` ใช้
        (``COALESCE(l.accounting_date, l.create_date)``) เพื่อให้สอง report ตัดรอบวันที่
        ตรงกันสำหรับเอกสาร backdate ทั้งสอง field เป็นคอลัมน์ตรงบน SVL เอง ไม่ใช่
        dotted path ข้าม model จึงไม่เข้าเคส correlated/bitmap-OR scan ที่เคยพบ
        (ดู memory ``svl-accounting-date-field``)
        """
        return [
            "|",
            ("accounting_date", operator, bound),
            "&", ("accounting_date", "=", False), ("create_date", operator, bound),
        ]

    # ==================================================================
    # Dimension maps
    # ==================================================================
    @api.model
    def _load_maps(self, opt):
        """แผนที่มิติทั้งหมด อ่านครั้งเดียวต่อรายงาน (groupby dotted path ไม่ได้ จึง map เอง)"""
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
        categories = self.env["product.category"].sudo().search_read(
            [], ["name", "complete_name"], order="complete_name", limit=2000
        )
        return {
            "location": location_map,
            "warehouse": warehouse_map,
            "warehouse_list": [
                {"id": wh["id"], "name": wh["name"], "code": wh["code"],
                 "company_id": wh["company_id"][0] if wh["company_id"] else 0}
                for wh in warehouses
            ],
            "categ_list": [
                {"id": c["id"], "name": c["name"], "complete_name": c["complete_name"]}
                for c in categories
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
        # read() ระบุฟิลด์ + load=False → ไม่คำนวณ display_name ของ m2o และไม่ไล่ prefetch ทีละ 1000
        # แล้วอ่านชื่อหมวด/หน่วยครั้งเดียวตาม id ที่พบ (แทนการแตะ related ต่อสินค้า)
        products = self._scoped("product.product", opt).sudo().browse(missing).read(
            ["name", "default_code", "categ_id", "uom_id", "tracking"], load=False,
        )
        uom_ids = {p["uom_id"] for p in products if p["uom_id"]}
        uom_names = {
            u["id"]: u["name"]
            for u in self.env["uom.uom"].sudo().search_read(
                [("id", "in", list(uom_ids))], ["name"]
            )
        } if uom_ids else {}
        categ_ids = {p["categ_id"] for p in products if p["categ_id"]} - set(maps["categ"])
        if categ_ids:
            for categ in self.env["product.category"].sudo().search_read(
                [("id", "in", list(categ_ids))], ["name", "complete_name"]
            ):
                maps["categ"][categ["id"]] = {
                    "name": categ["name"], "complete_name": categ["complete_name"],
                }
        for product in products:
            maps["product"][product["id"]] = {
                "name": product["name"],
                "default_code": product["default_code"] or "",
                "categ_id": product["categ_id"] or 0,
                "uom_name": uom_names.get(product["uom_id"], ""),
                "tracking": product["tracking"],
            }

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
    # Quantity ledger (คงเหลือ ณ วันที่ + ช่วงใช้งาน + วันจ่ายล่าสุด)
    # ==================================================================
    @api.model
    def _qty_groupby(self, opt):
        groupby = ["company_id", "product_id", "location_id", "location_dest_id"]
        if opt["group_lot"]:
            groupby.append("lot_id")
        return groupby

    @api.model
    def _fact_key(self, opt, company_id, loc_id, product_id, lot_id, maps):
        """คีย์ของโหนดที่ granularity ปัจจุบัน — location/lot เป็น 0 เมื่อระดับนั้นปิดอยู่"""
        info = maps["location"].get(loc_id) or {}
        return (
            company_id,
            info.get("warehouse_id", 0),
            product_id,
            loc_id if opt["group_location"] else 0,
            lot_id if opt["group_lot"] else 0,
        )

    @api.model
    def _unpack_row(self, row, opt, extra=0):
        """แกะแถวของ _read_group ตามลำดับ groupby (+ คอลัมน์เสริม) → (co, prod, src, dst, lot, *rest)"""
        if opt["group_lot"]:
            company, product, src, dst, lot = row[:5]
            rest = row[5:]
            lot_id = lot.id or 0
        else:
            company, product, src, dst = row[:4]
            rest = row[4:]
            lot_id = 0
        return company.id, product.id, src.id, dst.id, lot_id, rest

    @api.model
    def _read_qty_groups(self, opt, phase):
        """Q1 (ก่อนช่วง) / Q2 (ในช่วง) / Q_usage (ในช่วง เฉพาะการใช้จริง)"""
        domain = self._base_domain(opt)
        if phase == "opening":
            domain = domain + [("date", "<", opt["datetime_from"])]
        else:
            domain = domain + [
                ("date", ">=", opt["datetime_from"]),
                ("date", "<", opt["datetime_to"]),
            ]
        if phase == "usage":
            # การปรับปรุงยอด/ของเสียไม่ใช่ "การใช้" — ระบุใน domain เพราะ groupby ผ่าน move_id ไม่ได้
            domain += [("move_id.is_inventory", "=", False), ("move_id.scrapped", "=", False)]
        aggregates = ["quantity_product_uom:sum"]
        if phase != "usage":
            aggregates.append("date:max")
        return self._scoped("stock.move.line", opt)._read_group(
            domain, groupby=self._qty_groupby(opt), aggregates=aggregates,
        )

    @api.model
    def _emit_fact_row(self, company_id, product_id, src_id, dst_id, lot_id, qty, last_date,
                       phase, opt, maps, nodes, shadow, zone):
        """แปลงผลรวมหนึ่งก้อนเป็น fact 0-2 ตัว — หัวใจของสถาปัตยกรรม

        ที่มาเป็นของคงคลัง → OUT ที่โหนดต้นทาง; ที่ไปเป็นของคงคลัง → IN ที่โหนดปลายทาง;
        ทั้งคู่ตกโหนดเดียวกัน → ไม่ปล่อย (ย้ายของในคลังเดียวกันไม่ใช่การรับหรือจ่าย)
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
            external = not dst.get("valued")
            if scope is None or src_id in scope:
                node = self._add_fact(nodes, src_key, phase, "out", qty, external, opt)
                if last_date and phase != "usage":
                    day = self._local_day(last_date, zone)
                    if not node["last_out"] or day > node["last_out"]:
                        node["last_out"] = day
            if shadow is not None:
                self._add_fact(shadow, src_key, phase, "out", qty, external, opt)
        if dst_key is not None:
            external = not src.get("valued")
            if scope is None or dst_id in scope:
                self._add_fact(nodes, dst_key, phase, "in", qty, external, opt)
            if shadow is not None:
                self._add_fact(shadow, dst_key, phase, "in", qty, external, opt)

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
        elif phase == "usage":
            if direction == "out" and external:
                node["usage_qty"] += qty
        elif direction == "in":
            node["in_qty"] += qty
        else:
            node["out_qty"] += qty
        return node

    @api.model
    def _ledger_nodes(self, opt, maps, stats):
        """สร้างโหนดใบ {key: measures} พร้อมชุดเงาที่ไม่ผ่านตัวกรองคลัง (ตัวหารกระจายมูลค่า)"""
        nodes = {}
        scoped = maps["location_scope"] is not None
        shadow = {} if scoped else None
        zone = pytz.timezone(opt["tz"])
        for phase in ("opening", "period"):
            for row in self._read_qty_groups(opt, phase):
                company_id, product_id, src_id, dst_id, lot_id, rest = self._unpack_row(row, opt)
                qty, last_date = rest[0] or 0.0, rest[1]
                self._emit_fact_row(
                    company_id, product_id, src_id, dst_id, lot_id, qty, last_date,
                    phase, opt, maps, nodes, shadow, zone,
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

    @api.model
    def _read_usage(self, opt, maps, nodes):
        """Q_usage — จำนวนที่ "ใช้" ในช่วง (ออกจากขอบเขตมูลค่าบริษัท ไม่นับปรับปรุงยอด/ของเสีย/โอนภายใน)"""
        zone = pytz.timezone(opt["tz"])
        for row in self._read_qty_groups(opt, "usage"):
            company_id, product_id, src_id, dst_id, lot_id, rest = self._unpack_row(row, opt)
            self._emit_fact_row(
                company_id, product_id, src_id, dst_id, lot_id, rest[0] or 0.0, None,
                "usage", opt, maps, nodes, None, zone,
            )

    # ==================================================================
    # FIFO layer walk
    # ==================================================================
    @api.model
    def _bucket_windows(self, opt):
        """หน้าต่างย้อนหลังตามขอบช่วงอายุ: [(bucket_index, dt_lo|None, dt_hi, granularity)]"""
        as_of = self._to_date(opt["date_to"])
        windows = []
        for spec in opt["buckets"]:
            index = int(spec["key"][1:])
            if spec["hi"] is not None:
                lo_dt, hi_dt = self._period_bounds(
                    as_of - timedelta(days=spec["hi"]), as_of - timedelta(days=spec["lo"]), opt["tz"]
                )
                windows.append((index, lo_dt, hi_dt, "day"))
            else:
                _lo_dt, hi_dt = self._period_bounds(
                    as_of - timedelta(days=spec["lo"]), as_of - timedelta(days=spec["lo"]), opt["tz"]
                )
                # หน้าต่างสุดท้ายก็ยังใช้ระดับวัน — อายุเฉลี่ย/วันไม่เคลื่อนไหวของของเก่าต้องเป๊ะเหมือนกัน
                windows.append((index, None, hi_dt, "day"))
        return windows

    @api.model
    def _bucket_index(self, age, edges):
        for index, edge in enumerate(edges):
            if age <= edge:
                return index
        return BUCKET_COUNT - 1

    @api.model
    def _remaining_to_layer(self, nodes, rounding):
        """โหนดที่ต้องจัดชั้น: คงเหลือ > 0 (ติดลบ/ศูนย์ไม่จัดชั้น → flag negative)"""
        return {
            key: node["closing_qty"] for key, node in nodes.items()
            if node["closing_qty"] > 0 and not float_is_zero(node["closing_qty"], precision_rounding=rounding)
        }

    @api.model
    def _walk_layers(self, opt, maps, nodes, stats):
        """จัดชั้นอายุแบบ FIFO: ของที่เหลืออยู่คือของที่รับเข้าล่าสุด — **คิวรีเดียว**

        SQL window function หายอดสะสมของ IN fact ระดับวันต่อโหนดจากใหม่ไปเก่า แล้วส่งกลับเฉพาะ
        ชั้นที่ยังไม่พอคงเหลือ (``before < closing``) ประวัติ 100k+ บรรทัดจึงส่งข้าม DB มาแค่ไม่กี่แถว
        ต่อโหนด FROM/WHERE สร้างจาก ``_where_calc`` + ``_apply_ir_rules`` ของ ORM — domain, record rule
        และ multi-company เหมือน ``_read_group`` ทุกประการ กฎ fact (dst ต้อง on-hand, ย้ายในโหนดเดียวกัน
        ไม่ปล่อย, ก้อน (src,dst,วัน) ที่รวมแล้ว ≤ 0 ทิ้ง) อยู่ใน SQL ตัวเดียวกับ ``_emit_layer``
        ``_walk_layers_windowed`` คือเวอร์ชัน ORM เดิม เก็บไว้ให้เทสเทียบผลบิตต่อบิต
        """
        rounding = self._rounding(opt)
        remaining = self._remaining_to_layer(nodes, rounding)
        if not remaining:
            return
        rows = self._read_layers_sql(opt, remaining, stats)
        self._consume_layers(rows, nodes, remaining, opt, rounding)
        self._layer_leftovers(remaining, nodes, opt)

    @api.model
    def _read_layers_sql(self, opt, remaining, stats):
        """[(node_key, day, qty)] เรียงตามโหนดแล้ววันใหม่ → เก่า เฉพาะชั้นที่ต้องใช้"""
        products = sorted({key[K_PRODUCT] for key in remaining})
        model = self._scoped("stock.move.line", opt)
        domain = self._base_domain(opt) + [
            ("date", "<", opt["datetime_to"]),
            ("product_id", "in", products),
        ]
        # ค่าที่ค้างใน ORM cache ต้องลง DB ก่อน (คิวรีนี้ไม่ผ่าน _read_group จึงไม่ flush ให้เอง)
        self.env.flush_all()
        query = model._where_calc(domain)
        model._apply_ir_rules(query, "read")
        where = query.where_clause
        if not where:
            where = SQL("TRUE")

        group_location, group_lot = opt["group_location"], opt["group_lot"]
        day = SQL("(timezone(%s, timezone('UTC', \"stock_move_line\".\"date\")))::date", opt["tz"])
        values = SQL(", ").join(
            SQL("(%s, %s, %s, %s, %s, %s)", key[K_COMPANY], key[K_PRODUCT], key[K_WH],
                key[K_LOC], key[K_LOT], qty)
            for key, qty in remaining.items()
        )
        sql = SQL(
            """
            WITH pair AS (
                SELECT "stock_move_line"."company_id" AS company_id,
                       "stock_move_line"."product_id" AS product_id,
                       COALESCE(dst.warehouse_id, 0) AS wh,
                       %(loc)s AS loc,
                       %(lot)s AS lot,
                       %(day)s AS day,
                       SUM("stock_move_line"."quantity_product_uom") AS qty
                FROM %(from_clause)s
                JOIN stock_location dst ON dst.id = "stock_move_line"."location_dest_id"
                JOIN stock_location src ON src.id = "stock_move_line"."location_id"
                WHERE %(where)s
                  AND dst.usage = 'internal'
                  AND NOT (src.usage = 'internal'
                           AND COALESCE(src.warehouse_id, 0) = COALESCE(dst.warehouse_id, 0)
                           AND %(same_loc)s)
                GROUP BY "stock_move_line"."company_id", "stock_move_line"."product_id",
                         src.id, dst.id%(lot_group)s, %(day)s
                HAVING SUM("stock_move_line"."quantity_product_uom") > 0
            ), layer AS (
                SELECT company_id, product_id, wh, loc, lot, day, SUM(qty) AS qty
                FROM pair
                GROUP BY company_id, product_id, wh, loc, lot, day
            ), running AS (
                SELECT layer.*,
                       COALESCE(SUM(qty) OVER (
                           PARTITION BY company_id, product_id, wh, loc, lot
                           ORDER BY day DESC
                           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                       ), 0) AS before
                FROM layer
            )
            SELECT r.company_id, r.product_id, r.wh, r.loc, r.lot, r.day, r.qty
            FROM running r
            JOIN (VALUES %(values)s) AS node(company_id, product_id, wh, loc, lot, closing)
              ON node.company_id = r.company_id AND node.product_id = r.product_id
             AND node.wh = r.wh AND node.loc = r.loc AND node.lot = r.lot
            WHERE r.before < node.closing
            ORDER BY r.company_id, r.product_id, r.wh, r.loc, r.lot, r.day DESC
            LIMIT %(limit)s
            """,
            loc=SQL("dst.id") if group_location else SQL("0"),
            lot=SQL('COALESCE("stock_move_line"."lot_id", 0)') if group_lot else SQL("0"),
            lot_group=SQL(', "stock_move_line"."lot_id"') if group_lot else SQL(""),
            same_loc=SQL("src.id = dst.id") if group_location else SQL("TRUE"),
            day=day,
            from_clause=query.from_clause,
            where=where,
            values=values,
            limit=opt["max_layer_rows"] + 1,
        )
        self.env.cr.execute(sql)
        rows = self.env.cr.fetchall()
        stats["walk_windows_run"] += 1
        stats["layer_rows"] += len(rows)
        if len(rows) > opt["max_layer_rows"]:
            raise UserError(_(
                "ประวัติการรับเข้าที่ต้องอ่านมีมากกว่า %s แถว ซึ่งเกินขีดจำกัดที่ตั้งไว้\n\n"
                "ลองกรองคลัง หมวดสินค้า หรือสินค้าให้แคบลง"
            ) % opt["max_layer_rows"])
        return [
            ((company_id, wh, product_id, loc, lot), self._as_day(day), qty or 0.0)
            for company_id, product_id, wh, loc, lot, day, qty in rows
        ]

    @api.model
    def _consume_layers(self, rows, nodes, remaining, opt, rounding):
        """กินชั้นตามลำดับที่ให้มา (ต่อโหนด วันใหม่ → เก่า) จนคงเหลือของโหนดเต็ม"""
        as_of = self._to_date(opt["date_to"])
        edges = opt["bucket_edges"]
        for key, day, qty in rows:
            if key not in remaining or qty <= 0 or not day:
                continue
            node = nodes[key]
            take = min(remaining[key], qty)
            age = (as_of - day).days
            bucket = self._bucket_index(age, edges)
            node["b%d_qty" % bucket] += take
            node["age_qty_sum"] += age * take
            node["bucketed_qty"] += take
            if not node["newest_in"] or day > node["newest_in"]:
                node["newest_in"] = day
            if not node["oldest_in"] or day < node["oldest_in"]:
                node["oldest_in"] = day
            remaining[key] -= take
            if float_is_zero(remaining[key], precision_rounding=rounding) or remaining[key] < 0:
                del remaining[key]

    @api.model
    def _layer_leftovers(self, remaining, nodes, opt):
        """เศษที่จัดชั้นไม่ได้ — คงเหลือมากกว่า IN ทั้งประวัติ (ข้อมูลผิด/บรรทัดติดลบ) ไม่ปล่อยให้หายเงียบ"""
        edges = opt["bucket_edges"]
        for key, rem in remaining.items():
            node = nodes[key]
            node["b%d_qty" % (BUCKET_COUNT - 1)] += rem
            node["unlayered_qty"] += rem
            node["bucketed_qty"] += rem
            node["age_qty_sum"] += (edges[-1] + 1) * rem

    @api.model
    def _walk_layers_windowed(self, opt, maps, nodes, stats):
        """เวอร์ชัน ORM เดิม: อ่าน IN fact ระดับวันทีละหน้าต่างช่วงอายุ (ใหม่ → เก่า) ผ่าน ``_read_group``
        หยุดเมื่อทุกโหนดเต็ม — เก็บไว้เป็นตัวอ้างอิงให้เทสเทียบกับ ``_walk_layers`` (SQL) ไม่ใช้ในรายงานจริง
        """
        rounding = self._rounding(opt)
        remaining = self._remaining_to_layer(nodes, rounding)
        if not remaining:
            return
        model = self._scoped("stock.move.line", opt).with_context(tz=opt["tz"])
        base_domain = self._base_domain(opt)
        groupby_base = self._qty_groupby(opt)
        for _index, lo_dt, hi_dt, granularity in self._bucket_windows(opt):
            if not remaining:
                break
            domain = base_domain + [("date", "<", fields.Datetime.to_string(hi_dt))]
            if lo_dt is not None:
                domain.append(("date", ">=", fields.Datetime.to_string(lo_dt)))
            # กรองเฉพาะสินค้าที่ยังจัดชั้นไม่ครบเสมอ — หน้าต่างสุดท้าย (ไม่มีขอบล่าง) กวาดประวัติทั้งหมด
            # ถ้าไม่กรอง จะอ่านสินค้าที่เต็มไปแล้วตั้งแต่หน้าต่างแรกซ้ำ Postgres รับ IN หลายพันค่าได้สบาย
            domain.append(("product_id", "in", sorted({key[K_PRODUCT] for key in remaining})))
            # limit กันไม่ให้ดึงเกินโควตาข้าม DB มาก่อนแล้วค่อยปฏิเสธ
            rows = model._read_group(
                domain, groupby=groupby_base + ["date:%s" % granularity],
                aggregates=["quantity_product_uom:sum"], limit=opt["max_layer_rows"] + 1,
            )
            stats["walk_windows_run"] += 1
            stats["layer_rows"] += len(rows)
            if len(rows) > opt["max_layer_rows"]:
                raise UserError(_(
                    "ประวัติการรับเข้าที่ต้องอ่านมีมากกว่า %s แถว ซึ่งเกินขีดจำกัดที่ตั้งไว้\n\n"
                    "ลองกรองคลัง หมวดสินค้า หรือสินค้าให้แคบลง"
                ) % opt["max_layer_rows"])

            layers = {}
            for row in rows:
                company_id, product_id, src_id, dst_id, lot_id, rest = self._unpack_row(row, opt)
                day, qty = self._as_day(rest[0]), rest[1] or 0.0
                self._emit_layer(
                    company_id, product_id, src_id, dst_id, lot_id, qty, day, opt, maps,
                    layers, remaining,
                )
            self._consume_layers(
                [(key, day, days[day]) for key, days in layers.items()
                 for day in sorted(days, reverse=True)],
                nodes, remaining, opt, rounding,
            )
        self._layer_leftovers(remaining, nodes, opt)

    @api.model
    def _emit_layer(self, company_id, product_id, src_id, dst_id, lot_id, qty, day, opt, maps,
                    layers, remaining):
        """ครึ่ง IN ของกฎ fact — เก็บเฉพาะโหนดที่ยังจัดชั้นไม่ครบ"""
        if not qty or qty <= 0 or not day:
            return
        src = maps["location"].get(src_id) or {}
        dst = maps["location"].get(dst_id) or {}
        if not dst.get("on_hand"):
            return
        dst_key = self._fact_key(opt, company_id, dst_id, product_id, lot_id, maps)
        if src.get("on_hand"):
            src_key = self._fact_key(opt, company_id, src_id, product_id, lot_id, maps)
            if src_key == dst_key:
                return
        if dst_key not in remaining:
            return
        days = layers.setdefault(dst_key, {})
        days[day] = days.get(day, 0.0) + qty

    @api.model
    def _as_day(self, value):
        """ค่า ``date:day`` ของ _read_group — คืนเป็น ``date`` เสมอ"""
        if not value:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return fields.Date.to_date(str(value)[:10])

    @api.model
    def _local_day(self, stamp, zone):
        """วันตามเขตเวลาผู้ใช้ของ datetime แบบ naive-UTC (aggregate ``date:max`` ไม่แปลง tz ให้)"""
        if not stamp:
            return None
        value = fields.Datetime.to_datetime(stamp)
        return pytz.UTC.localize(value).astimezone(zone).date()

    # ==================================================================
    # Value
    # ==================================================================
    @api.model
    def _read_svl_closing(self, opt):
        """Q_svl — มูลค่า/จำนวนสะสม ณ วันที่ ต่อ (บริษัท, สินค้า) + ยอดคุมต่อบริษัท"""
        svl = self._svl_model(opt)
        domain = self._svl_domain(opt)
        # "ณ วันนี้" ไม่ต้องกรองวันที่ — ไม่งั้น subquery กวาดทั้งตาราง stock_move เปล่า ๆ
        if fields.Datetime.to_datetime(opt["datetime_to"]) < datetime.utcnow():
            domain += self._svl_date_domain(opt, "<", opt["datetime_to"])
        closing = {}
        control = {}
        for company, product, value, qty in svl._read_group(
            domain, groupby=["company_id", "product_id"], aggregates=["value:sum", "quantity:sum"],
        ):
            closing[(company.id, product.id)] = (value or 0.0, qty or 0.0)
            # ยอดคุมต่อบริษัทคือผลรวมของก้อนเดียวกัน ไม่ต้องอ่าน SVL รอบที่สอง
            control[company.id] = control.get(company.id, 0.0) + (value or 0.0)
        return {"closing": closing, "control": control}

    @api.model
    def _allocate_value(self, nodes, denominators, svl, opt):
        """กระจายมูลค่า SVL (ระดับบริษัท×สินค้า) ลงโหนดตามสัดส่วนคงเหลือ

        ตัวหารมาจากชุดเงาเมื่อกรองคลัง (ไม่งั้นคลังเดียวได้มูลค่าทั้งสินค้า); กรองล็อตใช้จำนวน
        SVL ทั้งบริษัทเป็นตัวหารแทน (SVL ไม่มีมิติล็อต) ผลรวมจึงกระทบ SVL เป๊ะเฉพาะรายงานที่
        ไม่ได้กรองคลัง/ที่เก็บ/ล็อต — ดู ``checks.svl_scope_limited``
        """
        by_product = {}
        for key, node in nodes.items():
            by_product.setdefault((key[K_COMPANY], key[K_PRODUCT]), []).append(node)
        denom_by_product = by_product
        if denominators is not nodes:
            denom_by_product = {}
            for key, node in denominators.items():
                denom_by_product.setdefault((key[K_COMPANY], key[K_PRODUCT]), []).append(node)
        exact = denominators is nodes and not opt["lot_ids"]
        if exact:
            # SVL อาจมีสินค้าที่ไม่มีจำนวนเลย (เศษมูลค่า) ถ้าไม่ดึงเข้ามาการกระทบยอดพัง
            for pair in svl["closing"]:
                by_product.setdefault(pair, [])

        for (company_id, product_id), group in by_product.items():
            amount, svl_qty = svl["closing"].get((company_id, product_id), (0.0, 0.0))
            if not amount:
                continue
            if opt["lot_ids"]:
                total = max(svl_qty, 0.0)
            else:
                total = sum(
                    max(n["closing_qty"], 0.0)
                    for n in denom_by_product.get((company_id, product_id), group)
                )
            if not total:
                if exact:
                    self._unassigned_node(nodes, group, company_id, product_id)["closing_value"] += amount
                continue
            allocated = 0.0
            last = None
            for node in group:
                weight = max(node["closing_qty"], 0.0)
                if not weight:
                    continue
                share = amount * weight / total
                node["closing_value"] += share
                allocated += share
                last = node
            if exact:
                # ยัดเศษเข้าโหนดสุดท้าย (หรือโหนดไม่ระบุคลัง) ผลรวมจึงเท่ากับ SVL บิตต่อบิต
                if last is not None:
                    last["closing_value"] += amount - allocated
                elif allocated != amount:
                    self._unassigned_node(nodes, group, company_id, product_id)["closing_value"] += amount

    @api.model
    def _unassigned_node(self, nodes, group, company_id, product_id):
        key = (company_id, 0, product_id, 0, 0)
        node = nodes.get(key)
        if node is None:
            node = nodes[key] = _zero_measures()
            group.append(node)
        elif node not in group:
            group.append(node)
        return node

    @api.model
    def _spread_bucket_values(self, nodes, opt, stats):
        """ซอย closing_value ของโหนดลงช่วงอายุตามสัดส่วนจำนวน — Σ ช่วง = closing_value เป๊ะ"""
        for node in nodes.values():
            value = node["closing_value"]
            if not value:
                continue
            total = node["bucketed_qty"]
            if total <= 0:
                stats["unbucketed_value"] += value
                continue
            allocated = 0.0
            last_key = None
            for qty_key, val_key in zip(BUCKET_QTY_KEYS, BUCKET_VAL_KEYS):
                qty = node[qty_key]
                if not qty:
                    continue
                share = value * qty / total
                node[val_key] += share
                allocated += share
                last_key = val_key
            if last_key is not None:
                node[last_key] += value - allocated

    # ==================================================================
    # Tree
    # ==================================================================
    @api.model
    def _node_path(self, key, opt, maps):
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
            return ("[%s]" % code if code else "", product.get("name", ""), "")
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
    def _new_slot(self, level, res_id):
        return {"level": level, "res_id": res_id, "measures": _zero_measures(),
                "children": {}, "keys": []}

    @api.model
    def _accumulate(self, target, measures):
        for mkey in ADDITIVE_KEYS:
            target[mkey] += measures[mkey]
        _merge_dates(target, measures)

    @api.model
    def _build_tree(self, nodes, opt, maps):
        """pivot โหนดใบเป็นต้นไม้ N ระดับ แล้วแบนเป็นลิสต์เรียงพร้อมแสดง

        คืน (lines, totals, product_risk) — product_risk คือสถานะที่ระดับ (บริษัท, สินค้า)
        ซึ่งไม่ขึ้นกับแกน/ระดับ/การกาง ใช้ทำ KPI "สินค้าเสี่ยง"
        """
        tree = {}
        by_product = {}
        for key, measures in nodes.items():
            path = self._node_path(key, opt, maps)
            cursor = tree
            for depth, (level, res_id) in enumerate(path):
                slot = cursor.setdefault((level, res_id), self._new_slot(level, res_id))
                self._accumulate(slot["measures"], measures)
                if depth == len(path) - 1:
                    slot["keys"].append(key)
                cursor = slot["children"]
            agg = by_product.setdefault((key[K_COMPANY], key[K_PRODUCT]), _zero_measures())
            self._accumulate(agg, measures)

        lines = []
        totals = _zero_measures()
        render = self._render_context(opt)
        rounding, decimals, as_of = render["rounding"], render["decimals"], render["as_of"]
        for slot in self._sorted_slots(tree, maps):
            branch = self._emit_slot(slot, "", 0, opt, maps, render, "", False)
            if not branch:
                continue
            branch[0]["counts_to_total"] = True
            # รวมจาก measure ดิบของ slot ไม่ใช่แถวที่ปัดเศษแล้ว (วันที่ในแถวเป็นสตริงแล้ว)
            self._accumulate(totals, slot["measures"])
            lines.extend(branch)
        grand = self._round_measures(totals, opt, rounding, decimals)
        grand.update(self._derive(totals, opt, rounding, with_metrics=False, as_of=as_of))
        grand.update({
            "kind": "grand_total",
            "id": "grand_total",
            "name": _("รวมทั้งสิ้น"),
            "code": "", "sub": "", "uom_name": "", "level": 0,
            "counts_to_total": False,
            "has_metrics": False,
        })

        product_risk = {"count": 0, "qty": 0.0, "value": 0.0, "product_count": 0}
        for measures in by_product.values():
            derived = self._derive(measures, opt, rounding, with_metrics=True, as_of=as_of)
            if not derived["status"]:
                continue
            product_risk["product_count"] += 1
            if derived["status"] in RISK_STATUSES:
                product_risk["count"] += 1
                product_risk["qty"] += measures["closing_qty"]
                product_risk["value"] += measures["closing_value"]
        return lines, grand, product_risk

    @api.model
    def _sorted_slots(self, mapping, maps):
        def sort_key(slot):
            code, name, _sub = self._node_label(slot["level"], slot["res_id"], maps)
            return (code or "￿", name or "")
        return sorted(mapping.values(), key=sort_key)

    @api.model
    def _render_context(self, opt):
        """ค่าคงที่ต่อการวาดทรีหนึ่งครั้ง — คำนวณครั้งเดียว ไม่ใช่ทุกแถว (บน prod มีหลายพันแถว)"""
        return {
            "rounding": self._rounding(opt),
            "decimals": self.env["res.company"].browse(opt["company_id"]).currency_id.decimal_places,
            "as_of": self._to_date(opt["date_to"]),
            "unfolded": set(opt["unfolded"]),
        }

    @api.model
    def _emit_slot(self, slot, parent_id, depth, opt, maps, render, uom_name, under_product):
        """แปลงโหนดหนึ่งเป็นแถว (พร้อมลูก ๆ ถ้ากางอยู่)

        ``under_product`` = แถวนี้อยู่ที่ระดับสินค้าหรือลึกกว่า → แสดงตัวชี้วัด No Move / ใช้เฉลี่ย /
        MOS / สถานะ; แถวเหนือสินค้า (คลัง/หมวด/บริษัท) แสดงแค่อายุเฉลี่ย ("-" ที่เหลือ ตามรูปแบบรายงาน)
        """
        rounding, decimals, as_of = render["rounding"], render["decimals"], render["as_of"]
        level, res_id = slot["level"], slot["res_id"]
        row_id = "%s/%s-%s" % (parent_id, LEVEL_PREFIX[level], res_id) if parent_id \
            else "%s-%s" % (LEVEL_PREFIX[level], res_id)
        measures = slot["measures"]
        if not self._keep_row(measures, opt, rounding):
            return []

        code, name, sub = self._node_label(level, res_id, maps)
        if level == "product":
            uom_name = maps["product"].get(res_id, {}).get("uom_name") or ""
            under_product = True
        children = self._sorted_slots(slot["children"], maps) if slot["children"] else []
        unfolded = depth < opt["unfold_level"] or row_id in render["unfolded"]

        line = self._round_measures(measures, opt, rounding, decimals)
        line.update(self._derive(measures, opt, rounding, with_metrics=under_product, as_of=as_of))
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
            "has_metrics": under_product,
            "flag": self._flag(measures, opt, rounding),
        })
        rows = [line]
        if not unfolded:
            return rows

        for child in children:
            rows.extend(
                self._emit_slot(child, row_id, depth + 1, opt, maps, render, uom_name, under_product)
            )
        if children:
            total = self._round_measures(measures, opt, rounding, decimals)
            total.update(self._derive(measures, opt, rounding, with_metrics=under_product, as_of=as_of))
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
                "has_metrics": under_product,
                "flag": "ok",
            })
            rows.append(total)
        return rows

    @api.model
    def _keep_row(self, measures, opt, rounding):
        if opt["display_product"] == "all":
            return True
        if measures["closing_value"]:
            return True
        return not float_is_zero(measures["closing_qty"], precision_rounding=rounding)

    @api.model
    def _rounding(self, opt):
        return 10 ** -opt["qty_precision"]

    @api.model
    def _round_measures(self, measures, opt, rounding, decimals=None):
        if decimals is None:
            decimals = self.env["res.company"].browse(opt["company_id"]).currency_id.decimal_places
        out = {}
        for key in QTY_KEYS:
            out[key] = float_round(measures[key], precision_rounding=rounding)
        for key in VAL_KEYS:
            out[key] = round(measures[key], decimals) if opt["show_value"] else 0.0
        out["age_qty_sum"] = round(measures["age_qty_sum"], 4)
        for key in DATE_KEYS:
            out[key] = fields.Date.to_string(measures[key]) if measures[key] else False
        return out

    @api.model
    def _derive(self, measures, opt, rounding, with_metrics, as_of=None):
        """ตัวชี้วัดที่บวกกันไม่ได้ — คำนวณจาก measure ที่บวกได้ของแถวนั้น ๆ ทุกครั้ง"""
        if as_of is None:
            as_of = self._to_date(opt["date_to"])
        bucketed = measures["bucketed_qty"]
        out = {
            "avg_age": round(measures["age_qty_sum"] / bucketed, 1) if bucketed > 0 else None,
            "no_move_days": None, "no_move_is_estimate": False,
            "avg_monthly_use": None, "mos": None, "status": None,
        }
        if not with_metrics:
            return out
        closing = measures["closing_qty"]
        if measures["last_out"]:
            out["no_move_days"] = (as_of - measures["last_out"]).days
        elif measures["oldest_in"]:
            out["no_move_days"] = (as_of - measures["oldest_in"]).days
            out["no_move_is_estimate"] = True
        avg_use = measures["usage_qty"] / opt["usage_months"] if opt["usage_months"] else 0.0
        out["avg_monthly_use"] = float_round(avg_use, precision_rounding=rounding)
        if avg_use > 0 and closing > 0:
            out["mos"] = round(closing / avg_use, 1)
        if closing <= 0 or float_is_zero(closing, precision_rounding=rounding):
            return out
        no_move = out["no_move_days"]
        if no_move is not None and no_move >= opt["obsolete_days"]:
            out["status"] = "obsolete"
        elif no_move is not None and no_move >= opt["non_moving_days"]:
            out["status"] = "non_moving"
        elif out["mos"] is None or out["mos"] > opt["slow_mos_months"]:
            out["status"] = "slow"
        else:
            out["status"] = "normal"
        return out

    @api.model
    def _flag(self, measures, opt, rounding):
        if measures["closing_qty"] < 0 and not float_is_zero(
            measures["closing_qty"], precision_rounding=rounding
        ):
            return "negative"
        if measures["unlayered_qty"] and not float_is_zero(
            measures["unlayered_qty"], precision_rounding=rounding
        ):
            return "unlayered"
        if opt["show_value"] and measures["closing_qty"] > 0 and not measures["closing_value"]:
            return "no_value"
        return "ok"

    # ==================================================================
    # KPI / checks / labels / columns
    # ==================================================================
    @api.model
    def _build_kpis(self, totals, product_risk, opt, currency):
        decimals = currency.decimal_places
        total_value = totals["closing_value"]
        total_qty = totals["closing_qty"]
        over = []
        edges = opt["bucket_edges"]
        for edge_index in (2, 3, 4):
            qty = sum(totals["b%d_qty" % i] for i in range(edge_index + 1, BUCKET_COUNT))
            value = sum(totals["b%d_value" % i] for i in range(edge_index + 1, BUCKET_COUNT))
            over.append({
                "edge": edges[edge_index],
                "qty": qty,
                "value": round(value, decimals) if opt["show_value"] else None,
                "pct_qty": round(qty / total_qty * 100, 1) if total_qty else None,
                "pct_value": round(value / total_value * 100, 1)
                             if opt["show_value"] and total_value else None,
            })
        return {
            "closing_qty": total_qty,
            "closing_value": total_value if opt["show_value"] else None,
            "avg_age": totals["avg_age"],
            "over": over,
            "risk": {
                "count": product_risk["count"],
                "product_count": product_risk["product_count"],
                "qty": float_round(product_risk["qty"], precision_rounding=self._rounding(opt)),
                "value": round(product_risk["value"], decimals) if opt["show_value"] else None,
            },
            "cards": {
                "opening_qty": totals["opening_qty"],
                "in_qty": totals["in_qty"],
                "out_qty": totals["out_qty"],
                "closing_qty": total_qty,
                "closing_value": total_value if opt["show_value"] else None,
            },
        }

    @api.model
    def _build_checks(self, lines, totals, svl, opt, currency, companies, stats):
        decimals = currency.decimal_places
        svl_value = sum((svl.get("control") or {}).values())
        report_value = totals["closing_value"]
        difference = round(report_value - svl_value, decimals)
        scope_limited = bool(opt["warehouse_ids"] or opt["location_ids"] or opt["lot_ids"])
        negative = [
            {"id": line["id"], "name": line["name"], "qty": line["closing_qty"]}
            for line in lines
            if line["kind"] == "group" and line.get("flag") == "negative"
        ][:20]
        other_currency = companies.filtered(lambda c: c.currency_id.id != currency.id)
        granularity = [LEVEL_LABEL[lv] for lv in ("wh", "loc", "lot") if lv in opt["levels"]]
        return {
            "show_value": opt["show_value"],
            "value_hidden_reason": opt["value_hidden_reason"],
            "cost_basis": opt["cost_basis"],
            "svl_value": round(svl_value, decimals),
            "report_value": round(report_value, decimals),
            "svl_difference": difference,
            "svl_scope_limited": scope_limited,
            "svl_reconciled": opt["show_value"] and not scope_limited and float_is_zero(
                difference, precision_rounding=currency.rounding
            ),
            "bucketed_qty": totals["bucketed_qty"],
            "bucket_qty_difference": float_round(
                totals["closing_qty"] - totals["bucketed_qty"], precision_rounding=self._rounding(opt)
            ),
            "unlayered_qty": totals["unlayered_qty"],
            "unbucketed_value": round(stats.get("unbucketed_value", 0.0), decimals),
            "no_move_estimated_rows": sum(
                1 for line in lines if line["kind"] == "group" and line.get("no_move_is_estimate")
            ),
            "age_granularity": " / ".join(granularity),
            "usage_window": {
                "date_from": opt["date_from"], "date_to": opt["date_to"],
                "months": opt["usage_months"],
            },
            "config_company": self.env["res.company"].browse(opt["company_id"]).name,
            "negative_balances": negative,
            "mixed_currency": [
                {"id": c.id, "name": c.name, "currency": c.currency_id.name}
                for c in other_currency
            ],
            "group_count": sum(1 for line in lines if line["kind"] == "group"),
            "layer_rows": stats.get("layer_rows", 0),
            "walk_windows_run": stats.get("walk_windows_run", 0),
            "has_stock_card": self._has_stock_card(),
        }

    @api.model
    def _build_labels(self, opt, maps):
        levels = " → ".join(LEVEL_LABEL[lv] for lv in opt["levels"])
        warehouses = ", ".join(
            maps["warehouse"].get(w, {}).get("name", str(w)) for w in opt["warehouse_ids"]
        )
        filters = []
        if opt["include_consignment"]:
            filters.append(_("รวมสินค้าฝากขาย"))
        if opt["product_search"]:
            filters.append(_("ค้นหา '%s'") % opt["product_search"])
        if opt["categ_ids"]:
            filters.append(_("%s หมวด") % len(opt["categ_ids"]))
        fmt = lambda value: self.format_report_date(value, opt["date_format"])  # noqa: E731
        return {
            "title": _("อายุสินค้าคงเหลือ (Stock Aging)"),
            "as_of": _("ณ วันที่ %s") % fmt(opt["date_to"]),
            "usage_window": _("ช่วงคำนวณการใช้ %s เดือน: %s – %s") % (
                opt["usage_months"], fmt(opt["date_from"]), fmt(opt["date_to"]),
            ),
            "companies": " + ".join(maps["company"].get(c, "") for c in opt["company_ids"]),
            "company_mode": _("รวมทุกบริษัท") if opt["company_mode"] == "consolidated"
                            else _("แยกตามบริษัท"),
            "levels": levels,
            "warehouses": warehouses or _("ทุกคลัง"),
            "age_basis": _("วันที่รับเข้าคลัง (FIFO)"),
            "cost_basis": _("ต้นทุนเฉลี่ย ณ วันที่ (กระทบ SVL)"),
            "thresholds": _("ช้า > %s MOS · ไม่เคลื่อนไหว ≥ %s วัน · ตาย ≥ %s วัน") % (
                opt["slow_mos_months"], opt["non_moving_days"], opt["obsolete_days"],
            ),
            "filters": " / ".join(filters) if filters else _("ไม่มีเงื่อนไขพิเศษ"),
            "timezone": opt["tz"],
        }

    @api.model
    def report_columns(self, report_data):
        """นิยามคอลัมน์ชุดเดียวของทุกช่องทาง (จอ / PDF / Excel) — หัวตาราง 2 ชั้น

        ``additive`` บอก Excel ว่าแถวรวมใช้ ``SUMPRODUCT`` ได้ (คอลัมน์อื่นเขียนค่าจาก totals)
        """
        opt = report_data["options"]
        show_value = opt["show_value"]
        columns = [
            {"group": "", "label": "รหัส", "key": "code", "type": "text", "additive": False},
            {"group": "", "label": "สินค้า", "key": "name", "type": "name", "additive": False},
            {"group": "", "label": "หน่วย", "key": "uom_name", "type": "uom", "additive": False},
            {"group": "คงเหลือ", "label": "จำนวน", "key": "closing_qty", "type": "qty", "additive": True},
        ]
        if show_value:
            columns.append({"group": "คงเหลือ", "label": "มูลค่า", "key": "closing_value",
                            "type": "money", "additive": True})
        for spec in report_data["buckets"]:
            group = "%s วัน" % spec["label"]
            columns.append({"group": group, "label": "จำนวน", "key": spec["key"] + "_qty",
                            "type": "qty", "additive": True, "bucket": spec["key"]})
            if show_value:
                columns.append({"group": group, "label": "มูลค่า", "key": spec["key"] + "_value",
                                "type": "money", "additive": True, "bucket": spec["key"]})
        columns += [
            {"group": "", "label": "อายุเฉลี่ย (วัน)", "key": "avg_age", "type": "days", "additive": False},
            {"group": "", "label": "วันไม่เคลื่อนไหว", "key": "no_move_days", "type": "days", "additive": False},
            {"group": "", "label": "ใช้เฉลี่ย/เดือน", "key": "avg_monthly_use", "type": "qty", "additive": False},
            {"group": "", "label": "MOS (เดือน)", "key": "mos", "type": "months", "additive": False},
            {"group": "", "label": "สถานะ", "key": "status", "type": "status", "additive": False},
        ]
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
        domain = self._base_domain(opt) + [("date", "<", opt["datetime_to"])]
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
            "name": _("รายการเคลื่อนไหว — %s") % self._drill_title(parts),
            "res_model": "stock.move.line",
            "view_mode": "list,form",
            # OWL doAction ไม่ผ่าน clean_action จึงต้องส่ง views มาเองให้ครบ
            "views": [(False, "list"), (False, "form")],
            "domain": domain,
            "context": {"create": False, "search_default_groupby_product_id": 1},
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
    def _drill_title(self, parts):
        if parts.get("prod"):
            product = self.env["product.product"].browse(parts["prod"]).exists()
            if product:
                return product.display_name
        if parts.get("wh"):
            warehouse = self.env["stock.warehouse"].browse(parts["wh"]).exists()
            if warehouse:
                return warehouse.display_name
        return _("อายุสินค้าคงเหลือ")
