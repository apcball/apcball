# 🔧 แก้ไขปัญหาปุ่ม Clear Advance (WHT) ค้าง - คำแนะนำการทดสอบ

## 📋 **สถานะปัจจุบัน**

✅ **การแก้ไขที่ทำไปแล้ว:**
- ปรับปรุงการแสดงปุ่มใน expense_sheet_views.xml
- เพิ่ม timeout protection ใน action_open_wht_clear_advance_wizard
- ปรับปรุง default_get ใน wizard พร้อม error handling
- เพิ่ม enhanced logging พร้อม emoji สำหรับ debugging

✅ **Logging ที่เพิ่มไป:**
- 🎯 WIZARD BUTTON CLICKED: เมื่อคลิกปุ่ม
- 🔍 WIZARD: ตรวจสอบ field values
- ✅ WIZARD: Method completed successfully
- 🎯 WIZARD DEFAULT_GET CALLED: เมื่อเริ่มสร้าง wizard

## 🧪 **วิธีการทดสอบ**

### **ขั้นตอนที่ 1: เตรียมการทดสอบ**

1. **เปิด Terminal สำหรับ monitor logs:**
```bash
sudo tail -f /var/log/odoo/instance1.log | grep -E "WIZARD|ERROR|exception"
```

2. **เปิด Browser Developer Console:**
   - กด F12
   - ไปที่ Tab "Console"
   - เพื่อดู JavaScript errors

### **ขั้นตอนที่ 2: ตรวจสอบ Expense Sheet**

ก่อนทดสอบ ให้ตรวจสอบว่า expense sheet มีเงื่นไขที่ถูกต้อง:

1. **เปิด Expense Sheet ที่ต้องการทดสอบ**
2. **เปิด Developer Mode** (Settings → Developer Tools → Activate Developer Mode)
3. **ตรวจสอบ Fields:**
   - `use_advance` = `True` ✅
   - `advance_box_id` = มีค่า (ไม่ใช่ False) ✅
   - `state` = `'approve'` ✅

**วิธีดู Field Values:**
- คลิกขวาที่ field → Inspect
- หรือดูใน Developer Tools

### **ขั้นตอนที่ 3: ทดสอบการคลิกปุ่ม**

1. **คลิกปุ่ม "Clear Advance (WHT)"** (ปุ่มสีเหลือง)

2. **สังเกต Logs ใน Terminal:**
   - ควรเห็น: `🎯 WIZARD BUTTON CLICKED: Starting Clear Advance (WHT) for expense sheet XXX`
   - ควรเห็น: `🔍 WIZARD: Checking use_advance: True`
   - ควรเห็น: `🔍 WIZARD: Checking advance_box_id: XX`
   - ควรเห็น: `🔍 WIZARD: Checking state: approve`
   - ควรเห็น: `✅ WIZARD: Method completed successfully, returning action`

3. **สังเกต Browser Console:**
   - ไม่ควรมี error สีแดง
   - ถ้ามี error ให้บันทึกข้อความ

### **ขั้นตอนที่ 4: วิเคราะห์ผลลัพธ์**

#### **🎉 กรณีที่ใช้งานได้:**
- เห็น logs ครบถ้วนตามขั้นตอน
- Wizard เปิดขึ้นมาปกติ
- ไม่มี error ใน browser console

#### **❌ กรณีที่ปุ่มไม่แสดง:**
- ตรวจสอบ field values อีกครั้ง
- ตรวจสอบว่า expense sheet ถูก approve แล้วหรือไม่

#### **⏳ กรณีที่ปุ่มค้าง:**
จะเห็น logs ข้อใดข้อหนึ่ง:

**A. ค้างที่ Method Call:**
```
🎯 WIZARD BUTTON CLICKED: Starting Clear Advance (WHT) for expense sheet XXX
(ไม่มีอะไรต่อ)
```
→ **สาเหตุ:** Method ไม่ถูกเรียก หรือมี error ก่อนเข้า try block

**B. ค้างที่ Validation:**
```
🎯 WIZARD BUTTON CLICKED: Starting Clear Advance (WHT) for expense sheet XXX
🔍 WIZARD: Method called successfully, processing...
🔍 WIZARD: Entering try block...
(ค้างตรงนี้)
```
→ **สาเหตุ:** Field access หรือ database query ช้า

**C. ค้างที่ Wizard Creation:**
```
... (logs ข้างบนครบ)
✅ WIZARD: Method completed successfully, returning action
🎯 WIZARD DEFAULT_GET CALLED: Starting with fields [...]
(ค้างตรงนี้)
```
→ **สาเหตุ:** Wizard default_get มีปัญหา

## 🔧 **การแก้ไขตามสาเหตุ**

### **หาก Method ไม่ถูกเรียก:**
1. ตรวจสอบว่าปุ่มแสดงหรือไม่
2. ตรวจสอบ JavaScript errors ใน browser console
3. Clear browser cache (Ctrl+Shift+R)

### **หาก Field Access ช้า:**
1. ตรวจสอบ database connection
2. Restart Odoo: `sudo systemctl restart instance1`

### **หาก Wizard Creation ช้า:**
1. ดู logs ต่อว่าติดตรงไหน
2. อาจต้องปรับปรุง default_get เพิ่มเติม

## 📞 **ขั้นตอนการรายงานปัญหา**

หากยังมีปัญหา กรุณาส่งข้อมูลต่อไปนี้:

1. **Logs จาก Terminal** (copy ทั้งหมดที่เกี่ยวข้อง)
2. **Browser Console Errors** (screenshot หรือ copy text)
3. **Field Values** จาก Developer Mode:
   - use_advance = ?
   - advance_box_id = ?
   - state = ?
4. **ขั้นตอนที่ทำ** ก่อนที่จะเกิดปัญหา

## 💡 **Tips เพิ่มเติม**

- **หากปุ่มไม่แสดง:** ตรวจสอบเงื่นไข 3 ข้อข้างต้น
- **หากค้างทุกครั้ง:** ลอง restart browser และ clear cache
- **หาก error ซ้ำ ๆ:** restart Odoo server
- **หากต้องการทดสอบเร็ว:** สร้าง expense sheet ใหม่แล้วทดสอบ

---

🚀 **พร้อมทดสอบแล้ว!** 
กรุณาทำตามขั้นตอนข้างต้นแล้วรายงานผลลัพธ์กลับมา เราจะได้แก้ไขปัญหาได้ตรงจุดมากขึ้น