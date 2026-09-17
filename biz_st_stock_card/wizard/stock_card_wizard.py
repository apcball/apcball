# -*- coding: utf-8 -*-
"""ตัวช่วยตั้งค่าและสั่งพิมพ์สต๊อกการ์ด

Wizard นี้เป็นแค่ "หน้ากรอกตัวกรอง" เท่านั้น ตัวเลขทุกตัวมาจาก
``biz.stock.card.report.get_report_data()`` ที่เดียว — ทั้งปุ่มบนหน้าจอ OWL และ
ปุ่มในไดอะล็อกนี้จบลงที่เมธอดเดียวกัน
"""

import base64

from odoo import _, api, fields, models


class StockCardWizard(models.TransientModel):
    _name = "biz.stock.card.wizard"
    _description = "Stock Card Wizard (สต๊อกการ์ด)"

    company_ids = fields.Many2many(
        "res.company", string="บริษัท", required=True,
        default=lambda self: self.env.companies,
        help="ค่าตั้งต้นคือบริษัทที่เลือกอยู่ใน company switcher",
    )
    is_multi_company = fields.Boolean(
        compute="_compute_is_multi_company",
        help="ใช้ซ่อน/แสดงตัวเลือกโหมดหลายบริษัทในฟอร์มเท่านั้น",
    )
    company_mode = fields.Selection(
        [("consolidated", "รวมทุกบริษัท"), ("split", "แยกแถวตามบริษัท")],
        string="หลายบริษัท", required=True, default="consolidated",
    )
    date_from = fields.Date(
        string="ตั้งแต่วันที่", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="ถึงวันที่", required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    group_mode = fields.Selection(
        [("wh_product", "คลัง → สินค้า"), ("product_wh", "สินค้า → คลัง")],
        string="จัดกลุ่มตาม", required=True, default="wh_product",
    )
    group_categ = fields.Boolean(string="แยกหมวดสินค้า")
    group_location = fields.Boolean(string="แยกที่เก็บย่อย")
    group_lot = fields.Boolean(string="แยกล็อต/ซีเรียล")

    warehouse_ids = fields.Many2many(
        "stock.warehouse", string="คลังสินค้า",
        domain="[('company_id', 'in', company_ids)]", help="ว่างไว้ = ทุกคลัง",
    )
    location_ids = fields.Many2many("stock.location", string="ที่เก็บ")
    product_ids = fields.Many2many("product.product", string="สินค้า")
    categ_ids = fields.Many2many("product.category", string="หมวดสินค้า")
    lot_ids = fields.Many2many("stock.lot", string="ล็อต/ซีเรียล")
    picking_type_ids = fields.Many2many("stock.picking.type", string="ประเภทการดำเนินการ")

    include_inventory = fields.Boolean(string="รวมการปรับปรุงยอด", default=True)
    include_scrap = fields.Boolean(string="รวมของเสีย", default=True)
    include_consignment = fields.Boolean(string="รวมสินค้าฝากขาย", default=False)

    show_value = fields.Boolean(string="แสดงมูลค่า", default=True)
    can_see_value = fields.Boolean(compute="_compute_can_see_value")
    value_mode = fields.Selection(
        [
            ("imputed", "ประมาณมูลค่าการโอนภายในคลัง"),
            ("svl", "เฉพาะมูลค่าที่มีชั้นมูลค่ารองรับ"),
        ],
        string="วิธีคิดมูลค่า", required=True, default="imputed",
    )
    value_date_basis = fields.Selection(
        [
            ("move", "วันที่ของการเคลื่อนไหว"),
            ("svl_create", "วันที่บันทึกมูลค่า"),
            # ต้องติดตั้ง stock_fifo_by_location (มีฟิลด์ accounting_date บน SVL)
            # ไม่มีก็ลดระดับกลับ "move" อัตโนมัติที่ตัวเครื่องยนต์ — ตรงกับเกณฑ์ของ
            # stock_fifo_valuation_report
            ("accounting", "วันที่บัญชี (ตรงกับรายงาน FIFO)"),
        ],
        string="เกณฑ์วันที่ของมูลค่า", required=True, default="move",
    )
    opening_basis = fields.Selection(
        [("moves", "ทุกรายการก่อนวันเริ่มงวด"), ("none", "ไม่คำนวณยอดยกมา")],
        string="เกณฑ์ยอดยกมา", required=True, default="moves",
    )
    display_product = fields.Selection(
        [
            ("movement", "เฉพาะที่มีความเคลื่อนไหวหรือมียอด"),
            ("not_zero", "เฉพาะที่ยอดคงเหลือไม่เป็นศูนย์"),
            ("all", "ทั้งหมด"),
        ],
        string="แสดงสินค้า", required=True, default="movement",
    )
    detail_mode = fields.Selection(
        [
            ("none", "ไม่แสดงรายการเคลื่อนไหว"),
            ("unfolded", "เฉพาะกลุ่มที่กางอยู่"),
            ("all", "ทั้งหมด (ต้องกรองสินค้าหรือหมวด)"),
        ],
        string="รายการเคลื่อนไหว", required=True, default="unfolded",
    )
    unfold_level = fields.Integer(string="กางถึงระดับ", default=1)
    date_format = fields.Selection(
        [("be", "พ.ศ."), ("ce", "ค.ศ.")], string="ปีที่แสดง", required=True, default="be",
    )

    xlsx_file = fields.Binary(string="ไฟล์ Excel", readonly=True, attachment=False)
    xlsx_filename = fields.Char(string="ชื่อไฟล์", readonly=True)

    @api.depends("company_ids")
    def _compute_is_multi_company(self):
        for wizard in self:
            wizard.is_multi_company = len(wizard.company_ids) > 1

    def _compute_can_see_value(self):
        can_see = self.env["biz.stock.card.report"]._can_see_value()
        for wizard in self:
            wizard.can_see_value = can_see

    @api.onchange("company_ids")
    def _onchange_company_ids(self):
        """ตัดคลังของบริษัทที่ถูกเอาออกทิ้ง ไม่งั้นตัวกรองจะค้างแล้วกรองว่าง"""
        self.warehouse_ids = self.warehouse_ids.filtered(
            lambda w: w.company_id in self.company_ids
        )

    # ------------------------------------------------------------------
    # Options bridge
    # ------------------------------------------------------------------
    def _get_options(self):
        self.ensure_one()
        return self.env["biz.stock.card.report"]._normalize_options({
            "company_ids": self.company_ids.ids,
            "company_mode": self.company_mode,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "group_mode": self.group_mode,
            "group_categ": self.group_categ,
            "group_location": self.group_location,
            "group_lot": self.group_lot,
            "warehouse_ids": self.warehouse_ids.ids,
            "location_ids": self.location_ids.ids,
            "product_ids": self.product_ids.ids,
            "categ_ids": self.categ_ids.ids,
            "lot_ids": self.lot_ids.ids,
            "picking_type_ids": self.picking_type_ids.ids,
            "include_inventory": self.include_inventory,
            "include_scrap": self.include_scrap,
            "include_consignment": self.include_consignment,
            "show_value": self.show_value,
            "value_mode": self.value_mode,
            "value_date_basis": self.value_date_basis,
            "opening_basis": self.opening_basis,
            "display_product": self.display_product,
            "detail_mode": self.detail_mode,
            "unfold_level": self.unfold_level,
            "date_format": self.date_format,
        })

    @api.model
    def _create_from_options(self, options):
        """สร้าง wizard ชั่วคราวจาก options ของหน้าจอ OWL เพื่อใช้เส้นทางพิมพ์เส้นเดียวกัน"""
        opt = self.env["biz.stock.card.report"]._normalize_options(options)
        return self.create({
            "company_ids": [(6, 0, opt["company_ids"])],
            "company_mode": opt["company_mode"],
            "date_from": opt["date_from"],
            "date_to": opt["date_to"],
            "group_mode": opt["group_mode"],
            "group_categ": opt["group_categ"],
            "group_location": opt["group_location"],
            "group_lot": opt["group_lot"],
            "warehouse_ids": [(6, 0, opt["warehouse_ids"])],
            "location_ids": [(6, 0, opt["location_ids"])],
            "product_ids": [(6, 0, opt["product_ids"])],
            "categ_ids": [(6, 0, opt["categ_ids"])],
            "lot_ids": [(6, 0, opt["lot_ids"])],
            "picking_type_ids": [(6, 0, opt["picking_type_ids"])],
            "include_inventory": opt["include_inventory"],
            "include_scrap": opt["include_scrap"],
            "include_consignment": opt["include_consignment"],
            "show_value": opt["show_value"],
            "value_mode": opt["value_mode"],
            "value_date_basis": opt["value_date_basis"],
            "opening_basis": opt["opening_basis"],
            "display_product": opt["display_product"],
            "detail_mode": opt["detail_mode"],
            "unfold_level": opt["unfold_level"],
            "date_format": opt["date_format"],
        })

    @api.model
    def action_export_from_options(self, options, output="pdf"):
        """เรียกจากปุ่มพิมพ์บนหน้าจอ OWL

        แถวที่กางอยู่บนจอถูกส่งต่อไปยังไฟล์ด้วย เพื่อให้สิ่งที่เห็นกับสิ่งที่พิมพ์ตรงกัน
        """
        wizard = self._create_from_options(options)
        opt = self.env["biz.stock.card.report"]._normalize_options(options)
        if output == "xlsx":
            return wizard.with_context(sc_unfolded=opt["unfolded"]).action_export_xlsx()
        return wizard.with_context(sc_unfolded=opt["unfolded"]).action_print_pdf()

    def _options_for_output(self):
        """options สำหรับ PDF/Excel — คงสถานะการกางจากหน้าจอไว้"""
        options = self._get_options()
        unfolded = self.env.context.get("sc_unfolded")
        if unfolded:
            options["unfolded"] = unfolded
            options = self.env["biz.stock.card.report"]._normalize_options(options)
        return options

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_view_report(self):
        """เปิดหน้าจอสต๊อกการ์ดแบบ interactive ด้วยตัวกรองชุดนี้"""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "biz_st_stock_card.action_stock_card_screen"
        )
        action["context"] = {"sc_options": self._get_options()}
        return action

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("biz_st_stock_card.action_report_stock_card").report_action(
            self, data={"options": self._options_for_output()}
        )

    def action_export_xlsx(self):
        self.ensure_one()
        options = self._options_for_output()
        content = self.env["biz.stock.card.xlsx"].generate(options)
        filename = _("สต๊อกการ์ด_%s_%s.xlsx") % (options["date_from"], options["date_to"])
        self.write({
            "xlsx_file": base64.b64encode(content),
            "xlsx_filename": filename,
        })
        return {
            "type": "ir.actions.act_url",
            "url": (
                "/web/content/?model=biz.stock.card.wizard&id=%s&field=xlsx_file"
                "&filename_field=xlsx_filename&download=true" % self.id
            ),
            "target": "self",
        }
