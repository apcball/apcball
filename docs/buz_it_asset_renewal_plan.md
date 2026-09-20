# แผนพัฒนา Software และระบบต่ออายุบริการใน `buz_it_asset`

เอกสารนี้เป็นแผนงานและ checklist สำหรับติดตามการพัฒนา โดยแยกชัดเจนว่าอะไรทำแล้ว อะไรกำลังทำ และอะไรยังไม่ทำ

สถานะเริ่มต้น: **ยังไม่ได้เริ่ม implementation**

วันที่จัดทำ: 2026-09-20

## สถานะภาพรวม

| งาน | สถานะ | หมายเหตุ |
|---|---|---|
| ตรวจสอบโครงสร้าง `buz_it_asset` เดิม | ทำแล้ว | ตรวจ model, view, security, manifest และ dashboard |
| ออกแบบโมเดลต่ออายุ | ทำแล้ว | ใช้โมเดลใหม่ แยกจาก Hardware เดิม |
| กำหนดขอบเขต Software | ทำแล้ว | ใช้ Software License เดิมเป็นข้อมูลหลัก |
| กำหนด workflow ยืนยันโดย IT | ทำแล้ว | Support Agent และ Manager ยืนยันได้ |
| เพิ่มโมเดล Python | ยังไม่ได้ทำ | รอเริ่ม implementation |
| เพิ่ม XML View/Menu | ยังไม่ได้ทำ | รอเริ่ม implementation |
| เพิ่ม Security/Access Rule | ยังไม่ได้ทำ | รอเริ่ม implementation |
| เพิ่ม Scheduled Action | ยังไม่ได้ทำ | เตือน 60/30/7 วัน |
| เพิ่ม Automated Tests | ยังไม่ได้ทำ | ต้องทดสอบ isolated Odoo |
| DEV deployment | ยังไม่ได้ทำ | ไม่อยู่ในขอบเขตงานปัจจุบัน |
| Production deployment | ยังไม่ได้ทำ | ต้องมีคำสั่งแยกต่างหาก |

## เป้าหมาย

พัฒนา `buz_it_asset` ให้รองรับการจัดการ Software และบริการที่ต้องต่ออายุแบบครบวงจร โดยคงข้อมูลและ workflow ของ Hardware เดิมไว้

ระบบต้องสามารถ:

- ใช้ Software Products, Software Licenses และ Installations เดิมต่อไป
- บันทึกบริการทั่วไป เช่น Domain, SSL, Hosting และ Internet
- รองรับรอบรายเดือน รายปี และจำนวนเดือนกำหนดเอง
- ให้ทีม IT ยืนยันการต่ออายุ
- เก็บประวัติการต่ออายุ ค่าใช้จ่าย ผู้ยืนยัน เวลา และหลักฐาน
- แจ้งเตือนล่วงหน้า 60, 30 และ 7 วัน
- แสดงรายการใกล้หมดอายุ หมดอายุ และประวัติการต่ออายุ
- ป้องกันการแก้ไขประวัติย้อนหลังและการสร้างกิจกรรมซ้ำ

## ขอบเขต

### อยู่ในขอบเขต

- Software License เดิมที่ผู้ดูแลเปิดใช้ระบบต่ออายุเป็นรายรายการ
- บริการทั่วไปที่ไม่จำเป็นต้องผูกกับ Asset หรือ Software License
- IT Support Agent และ Helpdesk Manager
- การแจ้งเตือนผ่าน `mail.activity` ใน Odoo
- ข้อมูลอ้างอิงด้านการเงิน เช่น ค่าใช้จ่าย เลขเอกสาร และไฟล์แนบ
- หน้ารายการต่ออายุและหน้าภาพรวมแยกจาก Dashboard เดิม

### อยู่นอกขอบเขต

- Hardware, Assignment และ Repair workflow
- การสร้าง Invoice หรือ Payment
- การเชื่อมต่อผู้ให้บริการภายนอก
- Email หรือ LINE notification
- การย้ายหรือ backfill ข้อมูลเดิมโดยอัตโนมัติ
- การ deploy ไป DEV หรือ Production ในงานพัฒนารอบนี้

## โครงสร้างที่เสนอ

### โมเดลเดิมที่ต้องคงไว้

| โมเดล | หน้าที่ | แนวทาง |
|---|---|---|
| `buz.it.software.product` | ชื่อโปรแกรม รุ่น และประเภท | ใช้ต่อโดยไม่เปลี่ยน workflow |
| `buz.it.software.license` | License, วันหมดอายุ, จำนวนสิทธิ์ | เป็นข้อมูลหลักของ Software |
| `buz.it.software.installation` | การติดตั้งและผู้ใช้งาน | ใช้ความสัมพันธ์เดิม |
| `buz.it.asset` | Hardware Asset | คงพฤติกรรมเดิมและอยู่นอกขอบเขต |

### โมเดลใหม่

| โมเดล | หน้าที่ |
|---|---|
| `buz.it.service.type` | ประเภทบริการทั่วไป เช่น Domain, SSL, Hosting |
| `buz.it.service` | รายการบริการทั่วไปและช่วงเวลาปัจจุบัน |
| `buz.it.renewal.profile` | การตั้งค่ารอบต่ออายุของ License หรือ Service |
| `buz.it.renewal.history` | ประวัติการยืนยันต่ออายุแต่ละรอบ |
| `buz.it.renewal.reminder` | บันทึกการเตือนเพื่อป้องกันกิจกรรมซ้ำ |

ข้อกำหนดความสัมพันธ์:

- หนึ่ง Renewal Profile เชื่อมกับ Software License หรือ Service อย่างใดอย่างหนึ่ง
- รายการเดิมที่ไม่เปิดใช้ Profile ต้องทำงานเหมือนเดิม
- Profile ไม่เก็บ License Key หรือข้อมูลโปรแกรมซ้ำ
- History เก็บ snapshot ของรอบเดิมและรอบใหม่สำหรับตรวจสอบย้อนหลัง
- ใช้ชื่อตารางใหม่ เช่น `buz_it_service_renewal` ห้ามใช้ชื่อตาราง legacy `buz_it_asset_renewal`

## การทำงานของ Software

Software ใช้ `buz.it.software.license` เดิมเป็น source of truth ของวันหมดอายุ เพื่อให้ Dashboard เดิมและการตรวจสอบตอนติดตั้งใช้ข้อมูลล่าสุดร่วมกัน

เมื่อเปิดใช้ Renewal Profile ให้กับ License:

1. ระบบแสดงปุ่ม `ยืนยันการต่ออายุ` ในส่วนต่ออายุของ License
2. IT ระบุวันเริ่มรอบใหม่ วันหมดอายุใหม่ ค่าใช้จ่าย และหลักฐาน
3. ระบบตรวจสอบข้อมูล License ล่าสุดและสิทธิ์ของผู้ใช้
4. ระบบสร้าง Renewal History
5. ระบบปรับ `start_date` และ `expiration_date` ของ License เดิม
6. ระบบปิดกิจกรรมเตือนของรอบเดิมและบันทึก chatter
7. ระบบสร้างการติดตามรอบใหม่

การปรับวันของ License ต้องเกิดผ่าน workflow ยืนยันที่ตรวจสอบ server-side เท่านั้น รายการที่ไม่ได้เปิดใช้ Profile ยังคงใช้วิธีเดิมได้

หมายเหตุ: โค้ดปัจจุบันมี `vendor_id` ใน License แต่ `create/write` ตัดค่านี้ออก จึงยังไม่เปลี่ยนพฤติกรรมเดิมในงานนี้ และให้ข้อมูลผู้ขายของรอบต่ออายุอยู่ในโมเดลใหม่ก่อน

## การทำงานของบริการทั่วไป

Service ใช้เก็บบริการที่ไม่จำเป็นต้องมี Software License หรือ Hardware Asset เช่น Domain, SSL, Hosting และ Internet

ข้อมูลหลักที่ต้องมี:

- ชื่อบริการและประเภทบริการ
- บริษัท
- ผู้ขาย
- ผู้รับผิดชอบ
- วันเริ่มต้นและวันหมดอายุ
- รอบบริการ: เดือน/ปี/จำนวนเดือนกำหนดเอง
- ค่าใช้จ่ายและสกุลเงิน
- เลขเอกสารและไฟล์แนบ
- สถานะการติดตาม

## Workflow การยืนยัน

สถานะการทำงาน:

- `draft`
- `active`
- `cancelled`

สถานะจากวันหมดอายุแสดงแยกเป็น:

- `upcoming`
- `due`
- `expired`

“ต่ออายุสำเร็จ” เป็นเหตุการณ์ใน Renewal History โดยต้องบันทึก:

- รายการเจ้าของการต่ออายุ
- รอบเดิมและรอบใหม่
- วันเวลาที่ยืนยัน
- ผู้ยืนยัน
- ค่าใช้จ่ายและเอกสาร
- หมายเหตุหรือเหตุผล

การยืนยันต้องทำใน transaction เดียว หากสร้างประวัติหรือปรับวันไม่สำเร็จ ต้อง rollback ทั้งชุด

การแก้ไขที่ยืนยันไปแล้วต้องสร้างรายการแก้ไขอ้างอิงประวัติเดิม ห้ามแก้ทับหรือลบ History

## Automation

Scheduled Action ทำงานวันละครั้ง โดย:

- เตือนล่วงหน้า 60, 30 และ 7 วัน
- สร้าง `mail.activity` ให้ผู้ใช้ที่ active ในกลุ่ม IT Support Agent หรือ Helpdesk Manager
- จำกัดตามบริษัทและสิทธิ์การเข้าถึงรายการ
- รวมผู้ใช้ที่อยู่ทั้งสองกลุ่มไม่ให้เกิดกิจกรรมซ้ำ
- สร้างกิจกรรมหมดอายุหนึ่งครั้งต่อรอบ
- ไม่สร้างกิจกรรมให้ Draft, Cancelled หรือรายการที่ปิดการติดตาม
- ใช้ `buz.it.renewal.reminder` ตรวจสอบการเตือนซ้ำ

หาก Scheduled Action หยุดทำงาน ระบบต้องเลือกเตือนระดับที่ใกล้วันปัจจุบันที่สุด ไม่สร้างกิจกรรมย้อนหลังทุกระดับพร้อมกัน

## สิทธิ์และความปลอดภัย

| กลุ่ม | สิทธิ์ |
|---|---|
| Requester | ไม่มีสิทธิ์จัดการ Renewal รุ่นแรก และสิทธิ์ Software เดิมคงเดิม |
| IT Support Agent | สร้าง/แก้ Service และยืนยันการต่ออายุที่เข้าถึงได้ |
| Helpdesk Manager | จัดการประเภทบริการ เปิดใช้ Profile ยกเลิก และบันทึกรายการแก้ไข |

กฎบังคับ:

- ตรวจ `company_id` ของ Service, License, Asset และ Vendor ที่เชื่อมโยง
- ตรวจสิทธิ์และสถานะใน Python model method ทุกครั้ง
- ห้ามพึ่ง XML `readonly` เพียงอย่างเดียว
- ห้ามใช้ context จาก client เพื่อข้าม workflow
- History และหลักฐานที่ยืนยันแล้วห้ามแก้ไขหรือลบ
- Profile ที่ active แล้วห้ามแก้วัน License โดยตรงผ่าน Import, RPC หรือ UI
- ป้องกันการยืนยันซ้ำและการยืนยันจากข้อมูลหน้าจอเก่า

## ผลกระทบ

### ผลกระทบที่ยอมรับได้

- เพิ่มตารางใหม่และฟิลด์เสริม
- เพิ่ม Views, Menu, ACL, Record Rules, Wizard และ Scheduled Action
- Module upgrade สร้าง metadata และตารางใหม่ตามปกติ
- License ที่เปิดใช้ Profile จะเปลี่ยนการปรับวันหมดอายุให้ผ่าน workflow ที่มีประวัติ
- Dashboard และการตรวจสอบ Software Installation จะเห็นวันหมดอายุ License ล่าสุด
- มี History, Attachment และ Activity เพิ่มขึ้น จึงต้องมี index และ domain ที่เหมาะสม

### สิ่งที่ต้องไม่กระทบ

- ข้อมูลและ ID เดิมของ Software Products, Licenses และ Installations
- จำนวนสิทธิ์และการติดตั้ง Software
- Hardware Asset, Assignment และ Repair
- Dashboard เดิมนอกส่วนข้อมูลต่ออายุที่เพิ่มใหม่
- Record Rule และ ACL เดิมของโมเดลที่ไม่เกี่ยวข้อง

## ข้อห้าม

- ห้ามเปลี่ยน schema หรือ workflow ของ Hardware, Assignment และ Repair
- ห้ามเปลี่ยนชื่อโมเดล ตาราง ฟิลด์ หรือ XML ID เดิม
- ห้ามสร้าง Software ซ้ำเป็น Service
- ห้ามย้าย License เดิมไปโมเดลใหม่
- ห้ามใช้ตาราง `buz_it_asset_renewal`
- ห้ามเปิด Profile หรือแก้วันเดิมอัตโนมัติระหว่าง module upgrade
- ห้ามเปลี่ยน License Key, Seats, Installations หรือเอกสารเดิมจากการยืนยัน
- ห้ามขยาย ACL ให้ Support Agent เขียน License ทุกฟิลด์
- ห้ามแก้หรือลบ Renewal History ที่ยืนยันแล้ว
- ห้ามสร้าง Invoice/Payment หรือถือว่าการยืนยันของ IT คือการชำระเงิน
- ห้ามแก้ migration เดิม
- ห้ามทดสอบบนฐานข้อมูลใช้งานจริง
- ห้าม deploy, upgrade หรือ restart DEV/Production โดยไม่มีคำสั่งแยก

## ลำดับการดำเนินงาน

### Phase 0: ตรวจสอบก่อนแก้

- [ ] ตรวจ `AGENTS.md` และขอบเขตโมดูล
- [ ] ตรวจ Git status และเก็บ baseline ของไฟล์เดิม
- [ ] ตรวจ model, view, security และ dashboard ที่ใช้วันหมดอายุ
- [ ] ตรวจ XML ที่เกี่ยวข้องทั้งหมดก่อนเพิ่ม inherited view
- [ ] ยืนยันว่าไม่มีโมเดลหรือตารางใหม่ชื่อซ้ำ

### Phase 1: Data model และ business logic

- [ ] เพิ่ม `buz.it.service.type`
- [ ] เพิ่ม `buz.it.service`
- [ ] เพิ่ม `buz.it.renewal.profile`
- [ ] เพิ่ม `buz.it.renewal.history`
- [ ] เพิ่ม `buz.it.renewal.reminder`
- [ ] เพิ่ม validation วันที่ รอบบริการ และบริษัท
- [ ] เพิ่ม workflow ยืนยันแบบ transaction เดียว
- [ ] เพิ่มการป้องกันแก้/ลบ History
- [ ] เพิ่มการป้องกันยืนยันซ้ำและ stale data

### Phase 2: Security และ UI

- [ ] เพิ่ม `ir.model.access.csv`
- [ ] เพิ่ม record rules ตามบริษัทและกลุ่มผู้ใช้
- [ ] เพิ่มเมนู Services, Renewals และ History
- [ ] เพิ่ม inherited view ใน Software License
- [ ] เพิ่ม Service tree/form/search view
- [ ] เพิ่ม Renewal wizard และมุมมองประวัติแบบอ่านอย่างเดียว
- [ ] เพิ่มหน้าภาพรวมต่ออายุแยกจาก Dashboard เดิม
- [ ] ตรวจ XML ID, XPath และ manifest load order

### Phase 3: Automation

- [ ] เพิ่ม Scheduled Action รายวัน
- [ ] เพิ่มการสร้างกิจกรรม 60/30/7 วัน
- [ ] เพิ่มการป้องกันกิจกรรมซ้ำ
- [ ] เพิ่มการปิดกิจกรรมเมื่อยืนยันต่ออายุ
- [ ] เพิ่มการติดตามรอบใหม่หลังยืนยัน
- [ ] ทดสอบกรณี job หยุดทำงานและกลับมาทำงานอีกครั้ง

### Phase 4: Tests และตรวจคุณภาพ

- [ ] ทดสอบติดตั้งใหม่บนฐานข้อมูลแยก
- [ ] ทดสอบ upgrade โดยมีข้อมูล Software เดิม
- [ ] ทดสอบ License ที่ไม่เปิด Profile ต้องทำงานเหมือนเดิม
- [ ] ทดสอบรอบรายเดือน รายปี และจำนวนเดือนกำหนดเอง
- [ ] ทดสอบวันสิ้นเดือนและปีอธิกสุรทิน
- [ ] ทดสอบต่อก่อนกำหนดและหลังหมดอายุ
- [ ] ทดสอบสิทธิ์ Support Agent, Manager และ Requester
- [ ] ทดสอบการยืนยันซ้ำและ concurrent update
- [ ] ทดสอบ company isolation และ attachment authorization
- [ ] ทดสอบการเตือน 60/30/7 วันโดยไม่ซ้ำ
- [ ] ทดสอบ Dashboard, Installations และ Hardware regression
- [ ] ตรวจ Python AST
- [ ] ตรวจ XML parse
- [ ] ตรวจ `git diff --check`
- [ ] รัน isolated Odoo tests และบันทึกผลลัพธ์

### Phase 5: ส่งมอบ

- [ ] ตรวจ source diff เฉพาะไฟล์ที่อยู่ในขอบเขต
- [ ] ตรวจว่าไม่มี generated artifact หรือไฟล์ต้องห้าม
- [ ] สรุปไฟล์ที่เพิ่มและพฤติกรรมที่เปลี่ยน
- [ ] สรุป test result และข้อจำกัดที่ยังไม่ได้ทำ
- [ ] รอคำสั่งแยกสำหรับ DEV deployment

## เกณฑ์ยอมรับ

งานจะถือว่าพร้อมส่งมอบเมื่อ:

- License เดิมที่ไม่เปิด Profile ยังทำงานเหมือนเดิม
- Software ที่เปิด Profile สามารถยืนยันและปรับวัน License เดิมได้อย่างปลอดภัย
- ทุกการยืนยันมี History และหลักฐานตรวจสอบย้อนหลัง
- บริการทั่วไปทำงานได้โดยไม่ต้องมี Asset หรือ License
- ระบบเตือนทำงานตาม 60/30/7 วันและไม่ซ้ำ
- History, สิทธิ์, company isolation และ attachment authorization ผ่านการทดสอบ
- Hardware, Assignment และ Repair ผ่าน regression check
- Isolated Odoo tests ผ่าน และไม่มี syntax/XML/diff error
- ไม่มีการย้าย ลบ หรือ backfill ข้อมูลเดิมโดยอัตโนมัติ

## บันทึกการเปลี่ยนแปลงแผน

| วันที่ | รายการ | สถานะ |
|---|---|---|
| 2026-09-20 | สร้างเอกสารแผนและ checklist | ทำแล้ว |
| 2026-09-20 | ยืนยันแนวทางใช้ Software License เดิมเป็น source of truth | ทำแล้ว |
| 2026-09-20 | ยืนยัน Hardware อยู่นอกขอบเขต | ทำแล้ว |
| 2026-09-20 | Implementation, test และ deployment | ยังไม่ได้ทำ |
