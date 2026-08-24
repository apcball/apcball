# -*- coding: utf-8 -*-
{
    "name": "Trial Balance (งบทดลอง)",
    "version": "17.0.1.3.0",
    "category": "Accounting",
    "summary": "งบทดลองแบบไทย — ยอดยกมา / เปลี่ยนแปลง / คงเหลือ รองรับหลายบริษัท พร้อมออก PDF และ Excel",
    "description": """
งบทดลอง (Trial Balance) ตามรูปแบบบัญชีไทย
==========================================

* คอลัมน์ 3 คู่ เดบิต/เครดิต — ยอดยกมา / เปลี่ยนแปลง / คงเหลือ + % เปลี่ยนแปลง
* จัดกลุ่ม 5 หมวดบัญชีไทย: สินทรัพย์ / หนี้สิน / ส่วนของเจ้าของ / รายได้ / ค่าใช้จ่าย
* เลือกเกณฑ์ยอดยกมาได้ — ต้นปีบัญชี หรือ ทุกรายการก่อนวันเริ่มงวด
* งบทดลองก่อนปิดบัญชี / หลังปิดบัญชี
* ตรวจดุลอัตโนมัติ และธงเตือนบัญชีที่มียอดผิดด้าน
* เปรียบเทียบงวดก่อน / ปีก่อน
* หลายบริษัท — เลือกบริษัทได้บนแถบตัวกรอง รวมเป็นงบเดียว หรือแยกแถวตามบริษัท
* ออกรายงาน PDF (ฟอนต์ไทย Sarabun ฝังในไฟล์) และ Excel (ยอดรวมเป็นสูตรตรวจย้อนได้)
    """,
    "author": "Biz",
    "license": "LGPL-3",
    "depends": [
        "account",
    ],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/trial_balance_wizard_views.xml",
        "report/trial_balance_templates.xml",
        "report/trial_balance_report.xml",
        "views/trial_balance_action.xml",
        "views/trial_balance_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "biz_ac_trial_balance/static/src/trial_balance/trial_balance.scss",
            "biz_ac_trial_balance/static/src/trial_balance/tb_format.js",
            "biz_ac_trial_balance/static/src/trial_balance/tb_filter_bar.js",
            "biz_ac_trial_balance/static/src/trial_balance/tb_filter_bar.xml",
            "biz_ac_trial_balance/static/src/trial_balance/tb_table.js",
            "biz_ac_trial_balance/static/src/trial_balance/tb_table.xml",
            "biz_ac_trial_balance/static/src/trial_balance/trial_balance.js",
            "biz_ac_trial_balance/static/src/trial_balance/trial_balance.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
