---
category: reference
created: 2026-05-16
sources: "[\"memory\"]"
tags: "[\"docker\", \"upgrade\", \"odoo\", \"command\"]"
title: Docker Upgrade Module Command
topic: คำสั่ง Docker สำหรับ upgrade module ใน workspace นี้ ใช้ทดสอบหลังสร้าง/แก้ไข module
updated: 2026-05-16
---

# Docker Upgrade Module Command
Description: คำสั่ง Docker สำหรับ upgrade module ใน workspace นี้ ใช้ทดสอบหลังสร้าง/แก้ไข module
---

คำสั่งสำหรับ upgrade module ใน database `MOG_DEV` ผ่าน Docker container ชื่อ `odoo`:

```bash
docker exec -it odoo odoo -d MOG_DEV -u <module_name> --stop-after-init --no-http
```

- `-d MOG_DEV` — database name
- `-u <module_name>` — module ที่ต้องการ upgrade
- `--stop-after-init` — หยุดทำงานหลัง upgrade เสร็จ
- `--no-http` — ไม่เปิด web server

ตัวอย่าง:
```bash
docker exec -it odoo odoo -d MOG_DEV -u buz_commercial_invoice --stop-after-init --no-http
```
