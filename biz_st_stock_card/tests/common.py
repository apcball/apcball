# -*- coding: utf-8 -*-
"""ฐานเทสของสต๊อกการ์ด

``odoo-dev`` เป็นฐานข้อมูลที่มีข้อมูลจริงอยู่แล้ว เทสจึงต้องสร้าง fixture ของตัวเอง
(สินค้า/คลังใหม่) และยืนยันกับ fixture นั้นเท่านั้น ห้าม assert ค่าสัมบูรณ์ทั้งระบบ
"""

import re
import zipfile
from datetime import datetime
from io import BytesIO
from xml.etree import ElementTree

from odoo import fields
from odoo.tests.common import TransactionCase

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def read_xlsx(content):
    """อ่าน .xlsx ด้วย stdlib — image ของโปรเจกต์นี้ไม่มี openpyxl

    :return: {ชื่อชีต: [[ค่าของเซลล์, ...], ...]} โดยสูตรคืนเป็นสตริงนำด้วย ``=``
    """
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


class StockCardCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.report = cls.env["biz.stock.card.report"]

        cls.wh_a = cls.env["stock.warehouse"].create({
            "name": "SC Warehouse A", "code": "SCA", "company_id": cls.company.id,
        })
        cls.wh_b = cls.env["stock.warehouse"].create({
            "name": "SC Warehouse B", "code": "SCB", "company_id": cls.company.id,
        })
        cls.stock_a = cls.wh_a.lot_stock_id
        cls.stock_b = cls.wh_b.lot_stock_id
        cls.shelf_a = cls.env["stock.location"].create({
            "name": "SC Shelf", "usage": "internal", "location_id": cls.stock_a.id,
            "company_id": cls.company.id,
        })
        cls.supplier = cls.env.ref("stock.stock_location_suppliers")
        cls.customer = cls.env.ref("stock.stock_location_customers")
        # ที่เก็บปรับปรุงยอดใน Odoo 17 เป็น company-dependent property ไม่มี xmlid กลาง
        # สร้างของเทสเองจึงชัดเจนและไม่ผูกกับข้อมูลของฐานข้อมูลที่ใช้ร่วมกัน
        cls.virtual = cls.env.ref("stock.stock_location_locations_virtual")
        cls.inventory_loss = cls.env["stock.location"].create({
            "name": "SC Inventory Adjustment", "usage": "inventory",
            "location_id": cls.virtual.id, "company_id": cls.company.id,
        })
        cls.scrap = cls.env["stock.location"].create({
            "name": "SC Scrap", "usage": "inventory", "scrap_location": True,
            "location_id": cls.virtual.id, "company_id": cls.company.id,
        })

        cls.categ = cls.env["product.category"].create({
            "name": "SC Category", "property_cost_method": "average",
            "property_valuation": "real_time",
        })
        cls.categ_other = cls.env["product.category"].create({
            "name": "SC Category Other", "property_cost_method": "average",
        })
        cls.product = cls._make_product("SC Widget", cls.categ, 10.0)
        cls.product_b = cls._make_product("SC Gadget", cls.categ_other, 25.0)
        cls.product_lot = cls._make_product("SC Tracked", cls.categ, 5.0, tracking="lot")

        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.uom_dozen = cls.env.ref("uom.product_uom_dozen")

        # งวดรายงานตายตัว ไม่ผูกกับวันนี้ เพื่อไม่ให้เทสพังตามปฏิทิน
        cls.date_from = "2025-06-01"
        cls.date_to = "2025-06-30"
        cls.before = datetime(2025, 5, 10, 3, 0, 0)
        cls.d1 = datetime(2025, 6, 5, 3, 0, 0)
        cls.d2 = datetime(2025, 6, 10, 3, 0, 0)
        cls.d3 = datetime(2025, 6, 20, 3, 0, 0)

    @classmethod
    def _make_product(cls, name, categ, cost, tracking="none"):
        return cls.env["product.product"].create({
            "name": name,
            "type": "product",
            "categ_id": categ.id,
            "standard_price": cost,
            "tracking": tracking,
        })

    # ------------------------------------------------------------------
    @classmethod
    def _do(cls, product, qty, src, dst, date, lot=None, uom=None, scrapped=False,
            owner=None):
        """สร้างและยืนยัน stock.move หนึ่งตัว แล้วบังคับวันที่ให้เป็นค่าที่ต้องการ

        ``_action_done()`` ประทับ ``fields.Datetime.now()`` ลงทั้ง move และ move line
        เสมอ จึงต้องเขียนทับหลังจบ ไม่งั้นทุกรายการจะไปกองอยู่ที่วันนี้และงวดคงที่
        ของเทสจะว่างเปล่า
        """
        uom = uom or product.uom_id
        move = cls.env["stock.move"].create({
            "name": "%s %s" % (product.name, qty),
            "product_id": product.id,
            "product_uom": uom.id,
            "product_uom_qty": qty,
            "location_id": src.id,
            "location_dest_id": dst.id,
            "company_id": cls.company.id,
        })
        move._action_confirm()
        move._action_assign()
        if not move.move_line_ids:
            move.write({"move_line_ids": [(0, 0, {
                "product_id": product.id,
                "product_uom_id": uom.id,
                "location_id": src.id,
                "location_dest_id": dst.id,
                "company_id": cls.company.id,
            })]})
        line = move.move_line_ids[0]
        vals = {"quantity": qty}
        if lot:
            vals["lot_id"] = lot.id
        if owner:
            # ต้องตั้งก่อน _action_done เพราะ core ใช้ owner_id ตัดสินว่าจะสร้าง
            # ชั้นมูลค่าหรือไม่ (_should_exclude_for_valuation) ตั้งทีหลังไม่มีผล
            vals["owner_id"] = owner.id
        line.write(vals)
        move.picked = True
        move._action_done()
        stamp = fields.Datetime.to_string(date)
        move.write({"date": stamp})
        move.move_line_ids.write({"date": stamp})
        if scrapped:
            move.write({"scrapped": True})
        return move

    @classmethod
    def _backdate_svl(cls, layers, date):
        """ย้อนวันที่ของชั้นมูลค่า

        ``stock.valuation.layer`` ไม่มีฟิลด์วันที่ เวลาของมันคือ ``create_date`` ซึ่ง
        core ประทับเป็นเวลาปัจจุบันเสมอ เทสที่ใช้งวดคงที่จึงต้องย้อนค่านี้เอง
        (โมดูล biz_mrp_backdate ก็ทำแบบเดียวกันในการใช้งานจริง)
        """
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
            "date_from": self.date_from,
            "date_to": self.date_to,
            "tz": "Asia/Bangkok",
            "product_ids": [self.product.id, self.product_b.id, self.product_lot.id],
        }
        options.update(kw)
        return options

    def _data(self, **kw):
        return self.report.get_report_data(self._options(**kw))

    def _row(self, data, row_id):
        for line in data["lines"]:
            if line["id"] == row_id:
                return line
        return None

    def _product_rows(self, data):
        return [
            line for line in data["lines"]
            if line["kind"] == "group" and line["group_type"] == "product"
        ]

    def _find(self, data, group_type, res_id):
        for line in data["lines"]:
            if (line["kind"] == "group" and line["group_type"] == group_type
                    and line["res_id"] == res_id):
                return line
        return None
