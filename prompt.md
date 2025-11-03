# Prompt Engineering: Odoo 17 Module – buz_direct_print_epson
**Objective:**  
สร้างโมดูล Odoo 17 ที่ช่วยให้ผู้ใช้สามารถเลือกเอกสารหลายใบ (เช่น Invoice, Picking, Bill) แล้วสั่งพิมพ์ตรงไปยังเครื่องพิมพ์ Epson (continuous form) ที่อยู่ใน Office ผ่าน Local Print Agent (HTTP API)

---

## 🎯 Functional Concept
- Module name: `buz_direct_print_epson`
- Category: Technical / Printing Integration
- Depends: `base`, `account`, `stock`
- Version: `17.0.1.0.0`
- License: LGPL-3

### 🔹 Use Case
1. User อยู่บน Odoo Cloud
2. User เปิด List View ของ Invoices (หรืออื่น ๆ)
3. เลือกหลายใบ → คลิกปุ่ม `Action > พิมพ์ต่อเนื่อง (Epson)`
4. Odoo จะเรียก REST API ของ Local Print Agent ที่รันอยู่ใน Office
5. Agent จะดึง PDF จาก Odoo แล้วสั่งพิมพ์ออกเครื่อง Epson (ผ่าน Windows driver)

---

## ⚙️ Module Components

### 1️⃣ Settings
เพิ่มเมนูใน **Settings → Technical → Printing → Epson Print Configuration**

Model: `buz.epson.config`
Fields:
- `name`: ชื่อการตั้งค่า
- `agent_url`: URL ของ Local Print Agent เช่น `http://192.168.1.55:5000/print`
- `default_printer`: ชื่อ printer (เช่น Epson_LQ310)
- `active`: Boolean

### 2️⃣ Action Button
เพิ่มปุ่ม Action ใน model `account.move` และ `stock.picking`:
- Label: “พิมพ์ต่อเนื่อง (Epson)”
- Multi-record action (ใช้ใน list view)
- เมื่อคลิก → เรียก method `action_print_epson()`

### 3️⃣ Backend Logic
ไฟล์ `models/account_move.py` และ `models/stock_picking.py`:

- สำหรับแต่ละเอกสารที่เลือก:
  - ใช้ `self.env.ref('account.account_invoices')._render_qweb_pdf()` เพื่อสร้าง PDF
  - Encode PDF หรือ upload ไป /web/content
  - POST ไปยัง URL จาก `buz.epson.config`
    ```python
    payload = {
        "printer": config.default_printer,
        "file_url": pdf_url,
        "type": "pdf",
    }
    requests.post(config.agent_url, json=payload, timeout=10)
    ```

- แสดง notification ว่า “ส่งพิมพ์สำเร็จแล้ว”

### 4️⃣ Views
- Menu: Settings → Technical → Printing → Epson Configuration
- List + Form View
- Action button ใน invoice list view

### 5️⃣ Security
- `security/ir.model.access.csv`
- ให้สิทธิ์กลุ่ม `base.group_system` แก้ไขการตั้งค่า Epson ได้

---

## 📂 Module Structure
buz_direct_print_epson/
├── init.py
├── manifest.py
├── models/
│ ├── init.py
│ ├── epson_config.py
│ ├── account_move.py
│ └── stock_picking.py
├── views/
│ ├── epson_config_view.xml
│ ├── account_move_view.xml
│ └── stock_picking_view.xml
├── security/
│ ├── ir.model.access.csv
│ └── security.xml
└── README.md

---

## 💻 Example API POST Body

```json
{
  "printer": "Epson_LQ310",
  "file_url": "https://odoo.mogth.work/report/pdf/account.move/INV/123",
  "type": "pdf"
}

🧠 Additional Notes

ใช้ requests module ใน Odoo (ต้อง import)

รองรับ multi-record selection

Error handling:

ถ้า agent ไม่ตอบ → แสดง warning popup

ถ้า success → แสดง toast “ส่งพิมพ์แล้ว”

🧾 Example Python Snippet (core logic)
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = "account.move"

    def action_print_epson(self):
        config = self.env["buz.epson.config"].search([("active", "=", True)], limit=1)
        if not config:
            raise UserError(_("Please configure Epson Print Agent first."))

        for record in self:
            pdf = self.env.ref("account.account_invoices")._render_qweb_pdf([record.id])[0]
            attachment = self.env["ir.attachment"].create({
                "name": f"{record.name}.pdf",
                "type": "binary",
                "datas": base64.b64encode(pdf),
                "res_model": record._name,
                "res_id": record.id,
                "mimetype": "application/pdf",
            })
            pdf_url = f"/web/content/{attachment.id}?download=true"

            payload = {
                "printer": config.default_printer,
                "file_url": self.env["ir.config_parameter"].sudo().get_param("web.base.url") + pdf_url,
                "type": "pdf"
            }

            try:
                requests.post(config.agent_url, json=payload, timeout=10)
            except Exception as e:
                raise UserError(_("Cannot connect to Epson agent:\n%s") % e)

        return True

🧩 Deliverables

รองรับ Invoice, Picking, Bill

มี config สำหรับ URL Agent และ Printer name

มี Action Button สำหรับพิมพ์ต่อเนื่อง (multi select)

ใช้ร่วมกับ Local Print Agent (Flask API)

🪄 Bonus (Optional)

เพิ่ม Auth Key ระหว่าง Odoo ↔ Agent

เพิ่ม Log การพิมพ์ใน model buz.epson.log

รองรับ Esc/POS Direct print mode (fast print)

Prompt Instruction:

สร้างโมดูล Odoo 17 ตามรายละเอียดข้างต้น พร้อมไฟล์ครบ (manifest, model, view, security, readme) และใช้ชื่อโมดูลว่า buz_direct_print_epson.

