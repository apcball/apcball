# -*- coding: utf-8 -*-
{
    "name": "Stock Card (สต๊อกการ์ด)",
    "version": "17.0.2.0.0",
    "category": "Inventory",
    "summary": "บัญชีคุมสินค้า — ยอดยกมา / รับ / จ่าย / คงเหลือ ทั้งจำนวนและมูลค่า "
               "แยกตามคลัง กางดูรายการเคลื่อนไหวได้ พร้อม PDF และ Excel",
    "description": """
สต๊อกการ์ด (Stock Card)
=======================

รายงานการเคลื่อนไหวสินค้าแบบบัญชีคุม ที่ Odoo Community ไม่มีให้:

* **ยอดยกมา / รับ / จ่าย / คงเหลือ** ทั้ง **จำนวน** และ **มูลค่า** ในตารางเดียว
* **สลับแกนการจัดกลุ่มได้ทันที** — คลัง → สินค้า หรือ สินค้า → คลัง
* ระดับเสริมเปิด-ปิดได้: หมวดสินค้า, ที่เก็บย่อย, ล็อต/ซีเรียล
* **กางดูรายการเคลื่อนไหวรายบรรทัด** พร้อมยอดคงเหลือสะสม (ดึงเฉพาะกิ่งที่กาง)
* Drill-down ไปยัง stock.move.line / stock.valuation.layer / ใบโอนย้ายได้
* รองรับหลายบริษัท (รวมงบ / แยกแถว) และเตือนเมื่อคนละสกุลเงิน
* ออก **PDF** (ฟอนต์ไทย Sarabun ฝังในไฟล์) และ **Excel** (ยอดรวมเป็นสูตร)

เครื่องยนต์เดียว
----------------

หน้าจอ, PDF และ Excel เรียก ``biz.stock.card.report.get_report_data()`` ตัวเดียวกัน
ห้ามมีเส้นทางคำนวณเส้นที่สอง ไม่งั้นตัวเลขบนจอกับในไฟล์จะเพี้ยนจากกันเงียบ ๆ

การกระทบยอดมูลค่า
------------------

มูลค่าทุกงวดกระทบกับ ``stock.valuation.layer`` ได้เสมอ และรายงานแสดงผลการกระทบยอด
นั้นให้เห็นทุกครั้ง (``checks.svl_reconciled``) — ดู README สำหรับข้อจำกัดที่ทราบ
    """,
    "author": "Biz",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "stock_account",
    ],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/stock_card_wizard_views.xml",
        "report/stock_card_templates.xml",
        "report/stock_card_report.xml",
        "views/stock_card_action.xml",
        "views/stock_card_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "biz_st_stock_card/static/src/stock_card/stock_card.scss",
            "biz_st_stock_card/static/src/stock_card/product_card.scss",
            "biz_st_stock_card/static/src/stock_card/sc_format.js",
            "biz_st_stock_card/static/src/stock_card/sc_shared.js",
            "biz_st_stock_card/static/src/stock_card/sc_axis_toggle.js",
            "biz_st_stock_card/static/src/stock_card/sc_axis_toggle.xml",
            "biz_st_stock_card/static/src/stock_card/sc_filter_bar.js",
            "biz_st_stock_card/static/src/stock_card/sc_filter_bar.xml",
            "biz_st_stock_card/static/src/stock_card/sc_table.js",
            "biz_st_stock_card/static/src/stock_card/sc_table.xml",
            "biz_st_stock_card/static/src/stock_card/stock_card.js",
            "biz_st_stock_card/static/src/stock_card/stock_card.xml",
            "biz_st_stock_card/static/src/stock_card/product_card.js",
            "biz_st_stock_card/static/src/stock_card/product_card.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
