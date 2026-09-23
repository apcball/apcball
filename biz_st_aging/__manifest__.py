# -*- coding: utf-8 -*-
{
    "name": "Stock Aging (อายุสินค้าคงเหลือ)",
    "version": "17.0.1.1.0",
    "category": "Inventory",
    "summary": "อายุสินค้าคงเหลือ ณ วันที่ — แยกช่วงอายุ FIFO ทั้งจำนวนและมูลค่า "
               "พร้อมวันไม่เคลื่อนไหว ใช้เฉลี่ย/เดือน MOS และสถานะ ออก PDF / Excel ได้",
    "description": """
อายุสินค้าคงเหลือ (Stock Aging)
================================

รายงานอายุสินค้าคงเหลือที่ Odoo Community ไม่มีให้:

* **คงเหลือ ณ วันที่** แยกเป็นช่วงอายุ 6 ช่วง (ตั้งค่าขอบช่วงได้ต่อบริษัท) ทั้ง **จำนวน** และ **มูลค่า**
* อายุนับแบบ **FIFO จากวันที่รับเข้าคลัง** (ของที่เหลือคือของที่รับเข้าล่าสุด) จาก ``stock.move.line``
* **อายุเฉลี่ย / วันไม่เคลื่อนไหว / ใช้เฉลี่ยต่อเดือน / MOS (เดือน) / สถานะ** (ปกติ, ช้า, ไม่เคลื่อนไหว, ตาย)
* สลับแกน คลัง → สินค้า หรือ สินค้า → คลัง, เปิดระดับ หมวดสินค้า / ที่เก็บย่อย / ล็อต-ซีเรียล ได้
* KPI: มูลค่ารวม, อายุเฉลี่ย, มูลค่าเกิน 90/180/365 วัน, จำนวนสินค้าเสี่ยง
* ออก **PDF** (ฟอนต์ไทย Sarabun ฝังในไฟล์) และ **Excel** (ยอดรวมเป็นสูตร)

เครื่องยนต์เดียว
----------------

หน้าจอ, PDF และ Excel เรียก ``biz.stock.aging.report.get_report_data()`` ตัวเดียวกัน
มูลค่ากระทบกับ ``stock.valuation.layer`` ได้เสมอ และรายงานแสดงผลการกระทบยอดให้เห็นทุกครั้ง
    """,
    "author": "Biz",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "stock_account",
    ],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/stock_aging_security.xml",
        "security/ir.model.access.csv",
        "views/stock_aging_config_views.xml",
        "wizard/stock_aging_wizard_views.xml",
        "report/stock_aging_templates.xml",
        "report/stock_aging_report.xml",
        "views/stock_aging_action.xml",
        "views/stock_aging_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "biz_st_aging/static/src/stock_aging/stock_aging.scss",
            "biz_st_aging/static/src/stock_aging/ag_format.js",
            "biz_st_aging/static/src/stock_aging/ag_shared.js",
            "biz_st_aging/static/src/stock_aging/ag_filter_bar.js",
            "biz_st_aging/static/src/stock_aging/ag_filter_bar.xml",
            "biz_st_aging/static/src/stock_aging/ag_table.js",
            "biz_st_aging/static/src/stock_aging/ag_table.xml",
            "biz_st_aging/static/src/stock_aging/stock_aging.js",
            "biz_st_aging/static/src/stock_aging/stock_aging.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
