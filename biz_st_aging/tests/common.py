# -*- coding: utf-8 -*-
"""ฐานเทสของรายงานอายุสินค้าคงเหลือ

``odoo-dev`` เป็นฐานข้อมูลที่มีข้อมูลจริงอยู่แล้ว เทสจึงต้องสร้าง fixture ของตัวเอง
(สินค้า/คลังใหม่) และยืนยันกับ fixture นั้นเท่านั้น ห้าม assert ค่าสัมบูรณ์ทั้งระบบ

fixture มาตรฐาน (D = 2025-06-30, ช่วงใช้งาน 6 เดือน = 2025-01-01..2025-06-30):

* W  : IN 100 @D−100 (ทุน 10), IN 10 + OUT 10 @D−15, IN 50 @D−10 (ทุน 20), OUT 30 @D−5 → ลูกค้า
       → คงเหลือ 120 = 60 ในช่วง 0-30 (50@10 วัน + 10@15 วัน) + 60 ในช่วง 91-180 (@100 วัน)
* B  : (คลัง B) IN 40 @D−400 ไม่เคยจ่าย → ช่วง >365, ตาย
* C  : IN 60 @D−200 คลัง A แล้วโอน 20 A→B @D−20 → A: 40 @200 วัน, B: 20 @20 วัน
* L  : ล็อต L1 6 @D−50, L2 4 @D−5, OUT 3 จาก L2 @D−2
* G  : รับคืนจากลูกค้า 8 @D−7
* F  : ปรับปรุงยอด IN 15 @D−45, OUT 10 ไปที่เก็บปรับปรุงยอด @D−3
"""

import re
import zipfile
from datetime import datetime, timedelta
from io import BytesIO
from xml.etree import ElementTree

from odoo import fields
from odoo.tests.common import TransactionCase

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

AS_OF = datetime(2025, 6, 30, 3, 0, 0)


def days_ago(days, hour=3):
    return AS_OF.replace(hour=hour) - timedelta(days=days)


def read_xlsx(content):
    """อ่าน .xlsx ด้วย stdlib — image ของโปรเจกต์นี้ไม่มี openpyxl (สูตรคืนเป็นสตริงนำด้วย ``=``)"""
    archive = zipfile.ZipFile(BytesIO(content))
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target_by_rid = {
        rel.get("Id"): rel.get("Target").lstrip("/").replace("xl/", "")
        for rel in rels
    }
    shared = []
    if "xl/sharedStrings.xml" in archive.namelist():
        strings = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        shared = ["".join(node.itertext()) for node in strings.findall(_NS + "si")]

    sheets = {}
    for sheet in workbook.find(_NS + "sheets"):
        rid = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        path = "xl/" + target_by_rid[rid]
        tree = ElementTree.fromstring(archive.read(path))
        rows = []
        for row in tree.iter(_NS + "row"):
            cells = {}
            for cell in row.findall(_NS + "c"):
                index = _column_index(cell.get("r"))
                formula = cell.find(_NS + "f")
                if formula is not None:
                    cells[index] = "=" + (formula.text or "")
                    continue
                value = cell.find(_NS + "v")
                if value is None:
                    cells[index] = None
                elif cell.get("t") == "s":
                    cells[index] = shared[int(value.text)]
                else:
                    try:
                        cells[index] = float(value.text)
                    except (TypeError, ValueError):
                        cells[index] = value.text
            width = max(cells) + 1 if cells else 0
            rows.append([cells.get(i) for i in range(width)])
        sheets[sheet.get("name")] = rows
    return sheets


def _column_index(ref):
    letters = re.match(r"([A-Z]+)", ref or "A").group(1)
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index - 1


class StockAgingCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.report = cls.env["biz.stock.aging.report"]
        # config ของบริษัทเป็นค่าตั้งต้นเสมอ — ฐานข้อมูลที่ใช้ร่วมกันอาจถูกแก้ไว้
        cls.config = cls.env["biz.stock.aging.config"].get_for_company(cls.company.id)
        cls.config.write({
            "bucket_1": 30, "bucket_2": 60, "bucket_3": 90, "bucket_4": 180, "bucket_5": 365,
            "usage_months": 6, "slow_mos_months": 6.0,
            "non_moving_days": 90, "obsolete_days": 365,
        })

        cls.wh_a = cls.env["stock.warehouse"].create({
            "name": "AG Warehouse A", "code": "AGA", "company_id": cls.company.id,
        })
        cls.wh_b = cls.env["stock.warehouse"].create({
            "name": "AG Warehouse B", "code": "AGB", "company_id": cls.company.id,
        })
        cls.stock_a = cls.wh_a.lot_stock_id
        cls.stock_b = cls.wh_b.lot_stock_id
        cls.shelf_a = cls.env["stock.location"].create({
            "name": "AG Shelf", "usage": "internal", "location_id": cls.stock_a.id,
            "company_id": cls.company.id,
        })
        cls.supplier = cls.env.ref("stock.stock_location_suppliers")
        cls.customer = cls.env.ref("stock.stock_location_customers")
        cls.virtual = cls.env.ref("stock.stock_location_locations_virtual")
        cls.inventory_loss = cls.env["stock.location"].create({
            "name": "AG Inventory Adjustment", "usage": "inventory",
            "location_id": cls.virtual.id, "company_id": cls.company.id,
        })

        cls.categ = cls.env["product.category"].create({
            "name": "AG Category", "property_cost_method": "average",
            "property_valuation": "real_time",
        })
        cls.categ_other = cls.env["product.category"].create({
            "name": "AG Category Other", "property_cost_method": "average",
        })
        cls.product_w = cls._make_product("AG Widget", cls.categ, 10.0, code="AGW")
        cls.product_b = cls._make_product("AG Bolt", cls.categ_other, 5.0, code="AGB1")
        cls.product_c = cls._make_product("AG Cable", cls.categ, 7.0, code="AGC")
        cls.product_l = cls._make_product("AG Lotted", cls.categ, 3.0, tracking="lot", code="AGL")
        cls.product_g = cls._make_product("AG Gasket", cls.categ_other, 2.0, code="AGG")
        cls.product_f = cls._make_product("AG Filter", cls.categ_other, 4.0, code="AGF")
        cls.all_products = (
            cls.product_w + cls.product_b + cls.product_c + cls.product_l
            + cls.product_g + cls.product_f
        )
        cls.date_to = "2025-06-30"

    @classmethod
    def _make_product(cls, name, categ, cost, tracking="none", code=None):
        return cls.env["product.product"].create({
            "name": name,
            "default_code": code,
            "type": "product",
            "categ_id": categ.id,
            "standard_price": cost,
            "tracking": tracking,
        })

    @classmethod
    def _seed_standard(cls):
        """fixture มาตรฐานตาม docstring ของไฟล์ — เรียกจาก setUpClass ของคลาสที่ต้องการ"""
        cls._do(cls.product_w, 100, cls.supplier, cls.stock_a, days_ago(100), price=10.0)
        cls._do(cls.product_w, 10, cls.supplier, cls.stock_a, days_ago(15, hour=2), price=10.0)
        cls._do(cls.product_w, 10, cls.stock_a, cls.customer, days_ago(15, hour=4))
        cls._do(cls.product_w, 50, cls.supplier, cls.stock_a, days_ago(10), price=20.0)
        cls._do(cls.product_w, 30, cls.stock_a, cls.customer, days_ago(5))

        cls._do(cls.product_b, 40, cls.supplier, cls.stock_b, days_ago(400), price=5.0)

        cls._do(cls.product_c, 60, cls.supplier, cls.stock_a, days_ago(200), price=7.0)
        cls._do(cls.product_c, 20, cls.stock_a, cls.stock_b, days_ago(20))

        cls.lot_1 = cls._lot(cls.product_l, "AG-L1")
        cls.lot_2 = cls._lot(cls.product_l, "AG-L2")
        cls._do(cls.product_l, 6, cls.supplier, cls.stock_a, days_ago(50), lot=cls.lot_1, price=3.0)
        cls._do(cls.product_l, 4, cls.supplier, cls.stock_a, days_ago(5), lot=cls.lot_2, price=3.0)
        cls._do(cls.product_l, 3, cls.stock_a, cls.customer, days_ago(2), lot=cls.lot_2)

        cls._do(cls.product_g, 8, cls.customer, cls.stock_a, days_ago(7), price=2.0)

        cls._do(cls.product_f, 15, cls.inventory_loss, cls.stock_a, days_ago(45), is_inventory=True)
        cls._do(cls.product_f, 10, cls.stock_a, cls.inventory_loss, days_ago(3), is_inventory=True)

    # ------------------------------------------------------------------
    @classmethod
    def _do(cls, product, qty, src, dst, date, lot=None, price=None, is_inventory=False,
            owner=None):
        """สร้างและยืนยัน stock.move หนึ่งตัว แล้วบังคับวันที่ให้เป็นค่าที่ต้องการ

        ``_action_done()`` ประทับ ``now()`` ลง move/move line เสมอ จึงต้องเขียนทับหลังจบ
        และย้อนวันที่ของชั้นมูลค่า (create_date) ให้ตรงกันด้วย
        """
        vals = {
            "name": "%s %s" % (product.name, qty),
            "product_id": product.id,
            "product_uom": product.uom_id.id,
            "product_uom_qty": qty,
            "location_id": src.id,
            "location_dest_id": dst.id,
            "company_id": cls.company.id,
        }
        if price is not None:
            vals["price_unit"] = price
        if is_inventory:
            vals["is_inventory"] = True
        move = cls.env["stock.move"].create(vals)
        move._action_confirm()
        move._action_assign()
        if not move.move_line_ids:
            move.write({"move_line_ids": [(0, 0, {
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "location_id": src.id,
                "location_dest_id": dst.id,
                "company_id": cls.company.id,
            })]})
        line = move.move_line_ids[0]
        line_vals = {"quantity": qty}
        if lot:
            line_vals["lot_id"] = lot.id
        if owner:
            line_vals["owner_id"] = owner.id
        line.write(line_vals)
        move.picked = True
        move._action_done()
        stamp = fields.Datetime.to_string(date)
        move.write({"date": stamp})
        move.move_line_ids.write({"date": stamp})
        if move.stock_valuation_layer_ids:
            cls._backdate_svl(move.stock_valuation_layer_ids, date)
        return move

    @classmethod
    def _backdate_svl(cls, layers, date):
        cls.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s WHERE id IN %s",
            (fields.Datetime.to_string(date), tuple(layers.ids)),
        )
        layers.invalidate_recordset(["create_date"])
        return layers

    @classmethod
    def _lot(cls, product, name):
        return cls.env["stock.lot"].create({
            "name": name, "product_id": product.id, "company_id": cls.company.id,
        })

    # ------------------------------------------------------------------
    def _options(self, **kw):
        options = {
            "company_ids": [self.company.id],
            "date_to": self.date_to,
            "tz": "Asia/Bangkok",
            "product_ids": self.all_products.ids,
        }
        options.update(kw)
        return options

    def _data(self, **kw):
        return self.report.get_report_data(self._options(**kw))

    def _rows(self, data, group_type=None, res_id=None, kind="group"):
        return [
            line for line in data["lines"]
            if line["kind"] == kind
            and (group_type is None or line["group_type"] == group_type)
            and (res_id is None or line["res_id"] == res_id)
        ]

    def _find(self, data, group_type, res_id, parent_prefix=None):
        for line in data["lines"]:
            if (line["kind"] == "group" and line["group_type"] == group_type
                    and line["res_id"] == res_id
                    and (parent_prefix is None or line["id"].startswith(parent_prefix))):
                return line
        return None

    def _product_row(self, data, product, warehouse=None):
        """แถวสินค้า — ในโหมด คลัง→สินค้า ระบุคลังได้"""
        prefix = "wh-%s/" % warehouse.id if warehouse else None
        return self._find(data, "product", product.id, prefix)

    def _buckets(self, line):
        return [line["b%d_qty" % i] for i in range(6)]
