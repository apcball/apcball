# -*- coding: utf-8 -*-
"""ตัวช่วยตั้งค่าและสั่งพิมพ์รายงานอายุสินค้าคงเหลือ

Wizard นี้เป็นแค่ "หน้ากรอกตัวกรอง" ตัวเลขทุกตัวมาจาก
``biz.stock.aging.report.get_report_data()`` ที่เดียว — ปุ่มบนหน้าจอ OWL และปุ่มใน
ไดอะล็อกนี้จบลงที่เมธอดเดียวกัน
"""

import base64

from odoo import _, api, fields, models


class StockAgingWizard(models.TransientModel):
    _name = "biz.stock.aging.wizard"
    _description = "Stock Aging Wizard (อายุสินค้าคงเหลือ)"

    company_ids = fields.Many2many(
        "res.company", string="บริษัท", required=True,
        default=lambda self: self.env.companies,
    )
    is_multi_company = fields.Boolean(compute="_compute_is_multi_company")
    company_mode = fields.Selection(
        [("consolidated", "รวมทุกบริษัท"), ("split", "แยกแถวตามบริษัท")],
        string="หลายบริษัท", required=True, default="consolidated",
    )
    date_to = fields.Date(
        string="ณ วันที่", required=True,
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
    include_consignment = fields.Boolean(string="รวมสินค้าฝากขาย", default=False)

    show_value = fields.Boolean(string="แสดงมูลค่า", default=True)
    can_see_value = fields.Boolean(compute="_compute_can_see_value")
    display_product = fields.Selection(
        [("on_hand", "เฉพาะที่มียอดคงเหลือ"), ("all", "ทั้งหมด")],
        string="แสดงสินค้า", required=True, default="on_hand",
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
        can_see = self.env["biz.stock.aging.report"]._can_see_value()
        for wizard in self:
            wizard.can_see_value = can_see

    @api.onchange("company_ids")
    def _onchange_company_ids(self):
        self.warehouse_ids = self.warehouse_ids.filtered(
            lambda w: w.company_id in self.company_ids
        )

    # ------------------------------------------------------------------
    # Options bridge
    # ------------------------------------------------------------------
    def _get_options(self):
        self.ensure_one()
        return self.env["biz.stock.aging.report"]._normalize_options({
            "company_ids": self.company_ids.ids,
            "company_mode": self.company_mode,
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
            "include_consignment": self.include_consignment,
            "show_value": self.show_value,
            "display_product": self.display_product,
            "unfold_level": self.unfold_level,
            "date_format": self.date_format,
        })

    @api.model
    def _create_from_options(self, options, normalized=False):
        """สร้าง wizard ชั่วคราวจาก options ของหน้าจอ OWL เพื่อใช้เส้นทางพิมพ์เส้นเดียวกัน"""
        opt = options if normalized else self.env["biz.stock.aging.report"]._normalize_options(options)
        return self.create({
            "company_ids": [(6, 0, opt["company_ids"])],
            "company_mode": opt["company_mode"],
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
            "include_consignment": opt["include_consignment"],
            "show_value": opt["show_value"],
            "display_product": opt["display_product"],
            "unfold_level": opt["unfold_level"],
            "date_format": opt["date_format"],
        })

    @api.model
    def action_export_from_options(self, options, output="pdf"):
        """เรียกจากปุ่มพิมพ์บนหน้าจอ OWL — แถวที่กางอยู่และช่องค้นหาถูกส่งต่อไปยังไฟล์ด้วย

        normalize ครั้งเดียว (แต่ละครั้งอ่าน config + ตรวจสิทธิ์บริษัท) แล้วส่ง options ที่พร้อมใช้
        ผ่าน context — wizard ยังถูกสร้างไว้เพื่อให้ PDF มี ``docs`` และ Excel มีที่เก็บไฟล์
        """
        opt = self.env["biz.stock.aging.report"]._normalize_options(options)
        wizard = self._create_from_options(opt, normalized=True).with_context(ag_options=opt)
        if output == "xlsx":
            return wizard.action_export_xlsx()
        return wizard.action_print_pdf()

    def _options_for_output(self):
        return self.env.context.get("ag_options") or self._get_options()

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_view_report(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "biz_st_aging.action_stock_aging_screen"
        )
        action["context"] = {"ag_options": self._get_options()}
        return action

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("biz_st_aging.action_report_stock_aging").report_action(
            self, data={"options": self._options_for_output()}
        )

    def action_export_xlsx(self):
        self.ensure_one()
        options = self._options_for_output()
        content = self.env["biz.stock.aging.xlsx"].generate(options)
        filename = _("อายุสินค้าคงเหลือ_%s.xlsx") % options["date_to"]
        self.write({
            "xlsx_file": base64.b64encode(content),
            "xlsx_filename": filename,
        })
        return {
            "type": "ir.actions.act_url",
            "url": (
                "/web/content/?model=biz.stock.aging.wizard&id=%s&field=xlsx_file"
                "&filename_field=xlsx_filename&download=true" % self.id
            ),
            "target": "self",
        }
