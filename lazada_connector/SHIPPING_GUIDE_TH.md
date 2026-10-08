# จัดส่ง Lazada เป็นชุดและดาวน์โหลดใบปะหน้า

สำหรับ Odoo 17 • ทำงานเหมือนเมนูจัดส่งเป็นชุดของ `shopee_connector` 17.0.2.2.0

## สถานะรุ่นนี้

> ตั้งแต่ 17.0.2.0.0 เมนู **Shipping Batches** และ Action **Lazada: Arrange shipment and labels** ถูกซ่อนไว้ เหมือนกับ Shopee 17.0.2.20.0 ตัวโค้ดยังอยู่ครบ ถ้าจะเปิดใช้ ให้ไปที่ Settings → Technical แล้วตั้ง menu เป็น active และผูก server action `action_lazada_create_shipping_batch` กับ Sale Order อีกครั้ง

โค้ดชุดนี้ต้องติดตั้งและทดสอบบนฐานข้อมูลทดสอบก่อนใช้งานจริง ระหว่างพัฒนายังไม่ได้ติดตั้งบน Odoo และยังไม่ได้เรียกบัญชี Lazada จริง ชุดทดสอบออฟไลน์ตรวจตรรกะและคำขอแบบจำลอง จึงยังยืนยันไม่ได้ว่าใช้ได้กับร้านและขนส่งทุกแบบ

## ต่างจาก Shopee ตรงไหน

- Lazada ไม่ให้เลือกนัดรับหรือนำส่งเองผ่าน API ค่า `delivery_type` ต้องเป็น `dropship` เสมอ ส่วนการนัดรับหรือนำส่งเองเป็นไปตามที่ตั้งค่าคลังสินค้าไว้ใน Seller Center ดังนั้นหน้านี้จึงไม่มีขั้นเลือกตัวเลือก dropoff/pickup และไม่มีช่องชื่อผู้ส่ง
- การจัดส่ง 1 ครั้งมี 2 คำสั่ง คือ **Pack** (`/order/fulfill/pack`) แล้วตามด้วย **Ready to Ship** (`/order/package/rts`) ซึ่งจะแจ้งขนส่งให้มารับหรือรอรับพัสดุ
- ใบปะหน้า (AWB) ได้จาก `/order/package/document/get` เป็น PDF ทันที ไม่ต้องรอสร้างงานเหมือน Shopee และไม่มีให้เลือก Normal/Thermal เพราะรูปแบบเป็นไปตามที่ตั้งไว้ใน Seller Center
- ออเดอร์ที่ Lazada แยกเป็นหลาย package ได้รับการรองรับ ระบบจะส่ง RTS ทุก package และได้ใบปะหน้าเป็น PDF ไฟล์เดียว

## ความสามารถ

- เลือกออเดอร์หลายรายการเพื่อสร้างชุดจัดส่ง สูงสุด 200 ออเดอร์ต่อชุด
- แต่ละชุดอยู่ในบริษัทเดียว รองรับหลายร้านในบริษัทนั้น โดยเรียก API ตามร้านของแต่ละออเดอร์
- อ่านสถานะสินค้าในออเดอร์จาก Lazada ก่อนทุกขั้นตอน ข้ามสินค้าที่ยกเลิกแล้ว
- ยืนยันเอกสารขาย Odoo ก่อนจัดส่งได้ โดยเปิดไว้เป็นค่าเริ่มต้น ออเดอร์ที่สินค้ายังไม่ครบหรือยังใช้ `LAZADA_UNMAPPED` จะถูกพักไว้
- ออเดอร์ที่ pack ใน Seller Center ไปแล้วจะไม่ถูก pack ซ้ำ ต้องกดคิวก่อน ระบบจึงจะส่ง Ready to Ship
- ออเดอร์ที่ Ready to Ship แล้วจะข้ามไปดึงใบปะหน้าอย่างเดียว
- ทำงานเบื้องหลัง แยกผลแต่ละออเดอร์ จึงไม่ต้องรอ API ทั้งชุดในหน้าเว็บ
- ดาวน์โหลด PDF รายออเดอร์ หรือ ZIP รวมไฟล์ที่พร้อมแล้ว พร้อม `results.csv` ของทุกออเดอร์
- ออเดอร์เดิมที่อยู่หลายชุดใช้ shipping job เดียวกัน ป้องกันการสร้างงานซ้ำ
- บันทึกเจตนาก่อนเรียก Pack และ Ready to Ship หาก timeout หรือโปรเซสหยุด งานจะพักไว้ให้ตรวจสถานะ ไม่ส่งคำสั่งเดิมซ้ำอัตโนมัติ

## ติดตั้ง/อัปเกรด

1. สำรองฐานข้อมูลและ filestore แล้วใช้ฐานข้อมูลทดสอบก่อน
2. วางโฟลเดอร์ `lazada_connector` ใน addons path ห้ามวางซ้อนเป็น `lazada_connector/lazada_connector`
3. ติดตั้ง `requests` ใน Python environment ของ Odoo (และติดตั้ง `openpyxl` ด้วยหากใช้การนำเข้า/ส่งออกสต็อก)
4. รีสตาร์ต Odoo แล้วอัปเกรดโมดูลจาก Apps หรือใช้คำสั่งตัวอย่างด้านล่าง โดยปรับชื่อฐานข้อมูลและ config ให้ตรงกับระบบ

```bash
odoo-bin -c /path/to/odoo.conf -d TEST_DATABASE -u lazada_connector --stop-after-init
```

5. ใช้บัญชีที่มีสิทธิ์ Sales Manager
6. ตรวจใน Scheduled Actions ว่า `Lazada: Shipping and Labels` เปิดใช้งานอยู่ และมี cron worker ทำงาน
7. ตรวจว่าแอปใน Lazada Open Platform ได้สิทธิ์ Order/Fulfillment แล้ว

## วิธีใช้

1. ไปที่ **Lazada → Orders** นำเข้าออเดอร์จากร้านที่เชื่อมต่อ แล้วตรวจสินค้า ราคา และยอดขาย
2. เลือกหลายออเดอร์ แล้วไปที่เมนู **Action → Lazada: Arrange shipment and labels / จัดส่งและใบปะหน้า**
3. ระบบจะเปิดหน้าชุดจัดส่ง รอ worker อ่านสถานะ แล้วรีเฟรชหน้าเว็บ ออเดอร์ที่พร้อมจะขึ้นสถานะ **Ready to queue**
4. หากต้องการปิดการยืนยันเอกสารขายของบางออเดอร์ ให้กด **Details / รายละเอียด** แล้วแก้ช่อง Confirm Odoo sale
5. กด **Queue ready orders / สั่งจัดส่งทั้งชุด** เพื่ออนุญาตให้ worker ยืนยันเอกสารขาย สั่ง Pack และ Ready to Ship บน Lazada
6. รอ worker ทำงานและรีเฟรชหน้า เมื่อสถานะเป็น **Label ready** ให้กด **Download ready labels (ZIP)**
7. แตก ZIP แล้วพิมพ์ PDF ที่ขนาดจริง 100% ตรวจ `results.csv` เพื่อดูรายการที่ยังไม่มีใบปะหน้า

## ความหมายของสถานะ

| สถานะ | สิ่งที่ต้องทำ |
|---|---|
| Loading order | รอ worker อ่านสถานะ แล้วรีเฟรช |
| Ready to queue | ตรวจแล้วกดคิว (ออเดอร์ที่ pack แล้วจะส่งเฉพาะ Ready to Ship) |
| Queued for shipment | รอ worker สั่ง Pack |
| Packed | Pack แล้ว รอ worker สั่ง Ready to Ship |
| Check shipment result | ผลของคำขอ Pack หรือ Ready to Ship ไม่ชัดเจน ให้ตรวจ Seller Center แล้วกด Reload / Check result |
| Shipment arranged | Ready to Ship แล้ว กำลังดึงใบปะหน้า |
| Label ready | ดาวน์โหลดได้ |
| Needs attention | อ่านข้อความสาเหตุ แก้ไข แล้วกด Reload หรือ Regenerate label ตามกรณี |

### เมื่อพบปัญหา

- **Timeout/5xx ระหว่าง Pack หรือ Ready to Ship:** ระบบจะไม่ส่งคำสั่งซ้ำ ให้ตรวจ Seller Center ก่อน ถ้าทำสำเร็จแล้วให้กด Reload ระบบจะอ่านสถานะใหม่แล้วไปขั้นถัดไป ถ้ายังไม่สำเร็จให้ทำต่อใน Seller Center รุ่นนี้ไม่มีปุ่มล้างสถานะที่ไม่แน่นอนเพื่อบังคับส่งใหม่
- **Lazada ปฏิเสธคำขอ (เช่น สถานะสินค้าเปลี่ยน):** งานจะขึ้น Needs attention พร้อมข้อความจาก Lazada แก้ไขแล้วกด Reload
- **Package หรือเลขพัสดุยังไม่พร้อม:** ระบบจะตรวจใหม่ทุกนาที สูงสุด 20 รอบ ถ้ายังไม่พร้อมจะขึ้น Needs attention ให้กด Reload ภายหลัง
- **ดึงใบปะหน้าไม่สำเร็จ:** กด Regenerate label ระบบจะขอ PDF ใหม่โดยไม่ Pack หรือ Ready to Ship ซ้ำ ลิงก์ PDF ของ Lazada มีอายุ 10 นาที ระบบจึงดาวน์โหลดเก็บทันที
- **สิทธิ์ผู้ขอเปลี่ยน:** งานเบื้องหลังทำงานด้วยสิทธิ์ของผู้ใช้ที่กดคิว ถ้าบัญชีถูกปิดหรือไม่มีสิทธิ์ในบริษัทแล้ว งานจะพักไว้

## ขอบเขตและข้อจำกัด

- รองรับเฉพาะร้านในประเทศ (`shipping_allocate_type = TFS` ให้ Lazada เลือกขนส่ง) ไม่รองรับร้าน cross-border (region `cb`)
- ไม่รองรับออเดอร์ดิจิทัล ออเดอร์ที่ร้านจัดส่งเอง (DBS/SOF) และออเดอร์ที่สถานะสินค้าปนกัน เช่นบางชิ้น pack แล้วบางชิ้นยัง ต้องจัดการใน Seller Center
- การจัดส่งบน Lazada ไม่ได้กด Validate ใบส่งสินค้าใน Odoo ไม่ได้ออกใบแจ้งหนี้ และไม่ได้จัดการการคืนหรือยกเลิกให้อัตโนมัติ
- ข้อมูลราคา ภาษี และส่วนลดจากตัวนำเข้าเดิมยังต้องตรวจก่อนยืนยัน
- worker ทำงานทุก 1 นาที สูงสุด 5 งานต่อรอบ และแต่ละงานทำทีละขั้น ชุดใหญ่จึงต้องใช้หลายรอบ
- ใบปะหน้ามีข้อมูลส่วนบุคคล ควรตั้งนโยบายเก็บและลบตามระบบขององค์กร รุ่นนี้ไม่ลบให้อัตโนมัติ
- ชื่อฟิลด์ใน response ของ Lazada (เช่น `package_id`, `tracking_code`, `pdf_url`) อ้างอิงจากเอกสาร Fulfillment ของ Lazada ต้องตรวจกับร้านจริงอีกครั้ง

## ทดสอบ

ทดสอบออฟไลน์ (ไม่ต้องใช้ Odoo แต่ต้องมี `requests`):

```bash
python lazada_connector/qa/test_shipping_offline.py
```

Odoo integration tests อยู่ใน `tests/test_fulfillment.py` ควรรันบนฐานข้อมูลทดสอบที่แยกจากระบบจริง:

```bash
odoo-bin -c /path/to/odoo.conf -d TEST_DATABASE -u lazada_connector --test-enable --test-tags /lazada_connector --stop-after-init
```

ก่อนใช้งานจริงควรผ่านกรณีต่อไปนี้: ติดตั้ง/อัปเกรด, ทดสอบสิทธิ์แยกบริษัท, ออเดอร์ 1 ชิ้น, ออเดอร์หลายชิ้น, ออเดอร์ที่มีสินค้ายกเลิกบางชิ้น, ออเดอร์ที่ pack ใน Seller Center ไปแล้ว, เลือกหลายออเดอร์ที่มีรายการล้มเหลวปนอยู่, และพิมพ์ทดสอบกับขนส่งที่ร้านใช้จริง

## แหล่งอ้างอิงสำหรับผู้ดูแล

- Lazada Fulfillment orders guide: https://open.lazada.com/apps/doc/doc?nodeId=43453&docId=121328
- ReadyToShip: https://open.lazada.com/apps/doc/api?path=%2Forder%2Fpackage%2Frts
- PrintAWB: https://open.lazada.com/apps/doc/api?path=%2Forder%2Fpackage%2Fdocument%2Fget
