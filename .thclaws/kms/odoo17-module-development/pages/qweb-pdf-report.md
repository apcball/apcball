---
category: report
created: 2026-05-15
sources: "[\"session-buz-unbuild-report\"]"
tags: "[\"qweb\", \"pdf\", \"report\", \"font\", \"sarabun\"]"
title: How to Create QWeb PDF Report in Odoo 17
topic: Step-by-step guide for adding a QWeb PDF report with custom Thai font to an Odoo 17 module
updated: 2026-05-15
---

# How to Create QWeb PDF Report in Odoo 17
Description: Step-by-step guide for adding a QWeb PDF report with custom Thai font to an Odoo 17 module
---

## ภาพรวม

การสร้าง QWeb PDF Report ใน Odoo 17 module มีขั้นตอนหลัก:
1. สร้าง report template XML
2. ลงทะเบียน font ใน `__manifest__.py`
3. เพิ่มปุ่ม Print ใน form view
4. เรียงลำดับ `data` ใน manifest ให้ report โหลดก่อน view

---

## 1. โครงสร้างไฟล์

```
module_name/
├── __manifest__.py
├── static/
│   └── fonts/
│       ├── Sarabun-Bold.ttf
│       ├── Sarabun-Regular.ttf
│       ├── Sarabun-Italic.ttf
│       └── Sarabun-BoldItalic.ttf
├── reports/
│   └── report_template.xml
└── views/
    └── form_view.xml
```

---

## 2. Report Template XML (`reports/report_template.xml`)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data>

        <!-- Paper Format -->
        <record id="paperformat_my_report" model="report.paperformat">
            <field name="name">My Report A4</field>
            <field name="default" eval="True"/>
            <field name="format">A4</field>
            <field name="orientation">Portrait</field>
            <field name="margin_top">10</field>
            <field name="margin_bottom">10</field>
            <field name="margin_left">6</field>
            <field name="margin_right">6</field>
            <field name="header_line" eval="False"/>
            <field name="header_spacing">0</field>
            <field name="dpi">90</field>
        </record>

        <!-- Report Action -->
        <record id="report_my_doc" model="ir.actions.report">
            <field name="name">My Report</field>
            <field name="model">my.model</field>
            <field name="report_type">qweb-pdf</field>
            <field name="report_name">module_name.report_my_doc_template</field>
            <field name="report_file">module_name.report_my_doc_template</field>
            <field name="print_report_name">'Report - %s' % (object.name or '')</field>
            <field name="paperformat_id" ref="module_name.paperformat_my_report"/>
            <field name="binding_model_id" ref="my_module.model_my_model"/>
            <field name="binding_type">report</field>
        </record>

        <!-- QWeb Template -->
        <template id="report_my_doc_template">
            <t t-call="web.html_container">
                <t t-foreach="docs" t-as="doc">
                    <t t-call="web.external_layout">
                        <style>
                            @font-face {
                                font-family: 'Sarabun';
                                src: url('/module_name/static/fonts/Sarabun-Bold.ttf') format('truetype');
                            }
                            .page {
                                font-family: 'Sarabun', sans-serif;
                            }
                            table, td, th, div, span, h2, h5, body {
                                font-family: 'Sarabun', sans-serif !important;
                                font-weight: bold;
                            }
                        </style>
                        <div class="page">
                            <!-- report content here -->
                        </div>
                    </t>
                </t>
            </t>
        </template>

    </data>
</odoo>
```

### จุดสำคัญของ font

- **path ต้องมี `/` นำหน้า**: `/module_name/static/fonts/Sarabun-Bold.ttf`
- **ต้องประกาศใน `__manifest__.py`** ด้วย (ดูข้อ 3)
- ใช้ `!important` เพื่อ override font ของ `web.external_layout`

---

## 3. ประกาศ Font ใน `__manifest__.py`

```python
{
    # ...
    "data": [
        "reports/report_template.xml",
        "views/form_view.xml",
    ],
    "assets": {
        "web.report_assets_common": [
            "/module_name/static/fonts/Sarabun-Bold.ttf",
        ],
    },
    # ...
}
```

**สำคัญ**: หากไม่ประกาศ font ใน `assets` → report จะใช้ system font แทน

---

## 4. เพิ่มปุ่ม Print ใน Form View

```xml
<button name="%(module_name.report_my_doc)d"
        type="action"
        string="Print"
        class="oe_highlight"
        groups="my_module.group_my_user"/>
```

---

## 5. ลำดับ `data` ใน Manifest — สำคัญมาก

**report XML ต้องอยู่ก่อน view XML** ที่อ้างถึง report action:

```python
"data": [
    "reports/report_template.xml",   # ← โหลดก่อน สร้าง external ID
    "views/form_view.xml",           # ← โหลดทีหลัง อ้างถึง external ID ได้
],
```

หากสลับลำดับ → `ValueError: External ID not found in the system` เพราะ view อ้าง `%(module_name.report_my_doc)d` ก่อนที่ report action จะถูกสร้าง

---

## 6. Paper Format Options

| Field | ค่าที่ใช้บ่อย | หมายเหตุ |
|-------|-------------|---------|
| `format` | `A4`, `Letter`, `Legal` | ขนาดกระดาษ |
| `orientation` | `Portrait`, `Landscape` | แนวกระดาษ |
| `margin_top/bottom/left/right` | `10`, `6` (mm) | ระยะขอบ |
| `dpi` | `90` | ความละเอียด |
| `header_line` | `True`/`False` | เส้นคั่น header |
| `header_spacing` | `0` | ระยะห่าง header |

---

## 7. ข้อผิดพลาดที่พบบ่อย

### External ID not found
```
ValueError: External ID not found in the system: module_name.report_my_doc
```
**สาเหตุ**: view โหลดก่อน report → สลับลำดับใน `data` ของ manifest

### Font ไม่ทำงาน ใช้ system font แทน
**สาเหตุได้แก่**:
1. ไม่ประกาศ font ใน `assets` → `web.report_assets_common` ของ manifest
2. path ใน `@font-face` ขาด `/` นำหน้า
3. ไฟล์ font ไม่อยู่ในตำแหน่งที่ถูกต้อง (`static/fonts/`)
