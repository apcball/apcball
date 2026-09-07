# buz_stock_count_adjust — ผลแก้บั๊ก

แก้ใน workspace เป็นเวอร์ชัน **17.0.1.1.0** ยังไม่ได้ deploy หรือ upgrade ฐาน Docker `MOG_LIVE` และไม่แก้ไข/สั่งงาน service ที่รันข้อมูลจริง

## สิ่งที่แก้

- Apply ย้อนทั้งงานเมื่อเกิด UserError หลังเริ่มเขียนสต็อก ส่วน Preview แยก savepoint ต่อกลุ่มและเก็บ error ได้โดยไม่ทิ้งการเปลี่ยนแปลงในฐาน
- การรวม movement ใน quant adjustment และ reconciliation ใช้ `quantity_product_uom` เพื่อรองรับหน่วยโหล/หน่วยแปลง ตรวจยอดจองเทียบ target ปัจจุบันหลังรวม movement และยอดของ quant ที่จะปรับ
- ปฏิเสธ layer ที่วันที่บัญชีกับวันที่สร้างอยู่คนละฝั่ง cutoff ก่อน reseed เพื่อป้องกัน replay นับซ้ำ **ยังไม่รองรับการจัดสรรรายการข้าม cutoff เหล่านี้โดยอัตโนมัติ**
- Backup เก็บ fingerprint ของ stock layers, quants, moves, move lines และ usage สำหรับสินค้าที่เกี่ยวข้อง ตรวจ membership และข้อมูลในแถวก่อน Rollback/Fix เพื่อปฏิเสธเมื่อมีการเปลี่ยนแปลงภายหลัง รวม reservation และ SQL writes ที่ไม่ได้เปลี่ยน write_date
- Snapshot quant ครอบคลุม virtual inventory counterpart ด้วย และ restore ค่า origin remaining ของ SVL เดิม
- Fix mismatch เก็บ pre-image แรกเท่านั้น ไม่เพิ่มภาพซ้ำของ quant/move line เดิม และปรับ fingerprint หลัง Fix สำเร็จ
- เพิ่ม company record rules ให้เอกสาร บรรทัด mismatch และ backup ทุกระดับ จำกัด backup/mismatch เป็น read-only สำหรับผู้ใช้ การเปลี่ยนผ่าน actions ตรวจสิทธิ์และบริษัทก่อน SQL mutation
- Hash ของ Preview รวม company/cutoff; เปลี่ยนหัวเอกสารแล้วกลับ Draft และล็อก input ของ Applied/Rolled Back ที่ฝั่ง model รวมกรณี default parent ผ่าน API
- Valuation Delta วัดผลต่าง `SUM(SVL.value)` ก่อนเริ่ม/หลังจบทุกขั้นตอน COGS Delta วัดผลต่าง signed outgoing SVL value หลัง cutoff ไม่ใช้ drift ระหว่าง replay รอบที่สอง

## การทดสอบ

ใช้ Odoo 17 image `my-odoo:17` และ PostgreSQL 16 ในคอนเทนเนอร์ชั่วคราวแยกจากระบบเดิม ฐานใหม่ชื่อ `MOG_SCA_TEST`, network ไม่มีการ publish port และใช้ namespace ของ PostgreSQL ทดสอบเท่านั้น Mount addon dependencies แบบ read-only พร้อม overlay โมดูลแก้ไขจาก temporary staging

คำสั่ง Odoo ที่ใช้ในรอบสุดท้าย:

```text
odoo --config=/dev/null --db_host=127.0.0.1 --db_user=sca_test --db_password=sca_test
  -d MOG_SCA_TEST -u buz_stock_count_adjust --without-demo=all
  --test-enable --test-tags=/buz_stock_count_adjust --stop-after-init --no-http
  --max-cron-threads=0 --workers=0 --data-dir=/tmp/sca-test-data
  --addons-path=/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
  --log-level=test
```

ผลจาก Odoo test runner วันที่ 7 กันยายน 2026 เวลา 03:10:40 UTC:

```text
71 post-tests in 13.91s, 32820 queries
0 failed, 0 error(s) of 71 tests when loading database 'MOG_SCA_TEST'
Container exit code: 0
```

ผ่าน Python AST parse, XML parse และ `git diff --check -- buz_stock_count_adjust` ด้วย ชุดทดสอบใหม่อยู่ที่ [test_regressions.py](../buz_stock_count_adjust/tests/test_regressions.py) และปรับชุดเดิมให้สอดคล้องกับ input immutability, verified backups และความละเอียดทศนิยมที่ฐานทดสอบกำหนด

รันทดสอบจากฐานใหม่ครั้งแรกและทดสอบ upgrade ซ้ำบนฐานชั่วคราว ไม่ใช่การ upgrade ฐาน Test ที่ผู้ใช้รัน SCA/00261 ไว้ หลังจบลบคอนเทนเนอร์ทั้ง 4 ตัว, disposable database volume และ temporary staging ที่สร้างสำหรับงานนี้แล้ว

## ข้อจำกัดเมื่อจะนำไปใช้

**Backup รุ่นเก่า รวมถึง backup 53 ของ SCA/00261 ไม่มี post-apply fingerprint จึงจะไม่อนุญาต automatic Rollback/Fix หลัง upgrade** การสร้าง fingerprint ให้ข้อมูลปัจจุบันย้อนหลังโดยไม่ตรวจประวัติจะรับรองสถานะผิด จึงไม่ได้เติมให้อัตโนมัติ ต้องตรวจและวางวิธีกู้คืนเฉพาะกรณีก่อนใช้งาน

Fingerprint ตั้งใจครอบคลุมสินค้าที่ได้รับผลกระทบทั้งบริษัท จึงอาจปฏิเสธ Rollback แม้การเปลี่ยนแปลงภายหลังอยู่คลังอื่น นี่เป็นข้อจำกัดแบบอนุรักษนิยมเพื่อไม่เขียนทับธุรกรรมใหม่

ค่ารายงาน Delta ของเอกสารที่ Applied ไปแล้วไม่ได้ถูกแก้ย้อนหลัง การเปลี่ยนคอลัมน์ origin quantity ใน FIFO report และการเลือก physical Lot/Serial ไม่อยู่ในการแก้ครั้งนี้

ตรวจ SHA-256 หลังทดสอบแล้ว Python/XML/CSV ทั้ง 18 ไฟล์ใน `/srv/docker/odoo_mogen/custom-addons/buz_stock_count_adjust` ยังตรงกับ source เดิมก่อนแก้ทั้งหมด
