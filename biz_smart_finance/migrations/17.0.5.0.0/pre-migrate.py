# -*- coding: utf-8 -*-
"""รายการกระแสเงินสดที่มีอยู่เดิมคือรายการที่ใช้งานจริงทั้งหมด

ฟิลด์ `state` ใหม่มีค่าตั้งต้นเป็น "confirmed" อยู่แล้ว แต่ ORM เติมค่าตั้งต้น
ให้แถวเดิมเฉพาะตอนสร้างคอลัมน์ — ถ้าคอลัมน์ถูกสร้างไว้ก่อนหน้าด้วยเหตุใดก็ตาม
แถวที่ค่าเป็น NULL จะหลุดจากกริดพยากรณ์เงียบ ๆ (engine กรอง state=confirmed)
จึงย้ำอีกชั้นที่นี่
"""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'biz_smart_finance_forecast_line'
          AND column_name = 'state'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE biz_smart_finance_forecast_line
        SET state = 'confirmed'
        WHERE state IS NULL
    """)
