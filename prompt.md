# Prompt Engineering – BUZ Validate Control Module (Odoo 17)

## 🎯 Objective
สร้างโมดูลที่ใช้ **ควบคุมการมองเห็นและสิทธิ์การกดปุ่ม Validate / Post** ในเอกสาร Odoo ให้เฉพาะกลุ่มผู้ใช้ที่ได้รับอนุญาตเท่านั้น เช่น กลุ่มผู้จัดการคลัง หรือหัวหน้าบัญชี

---

## 🧩 Module Name
`buz_validate_control`

---

## 🧠 Concept
- ซ่อนปุ่ม Validate (Stock Picking) และ Post (Account Move) จากผู้ใช้ทั่วไป
- แสดงเฉพาะผู้ใช้ในกลุ่ม `Validate Privileged`
- ป้องกันการ bypass ด้วยการเช็คสิทธิ์ในฝั่งเซิร์ฟเวอร์ (`has_group()`)
- สามารถขยายได้กับโมเดลอื่น เช่น `mrp.production` (ปุ่ม Mark as Done), `purchase.order` (Confirm)

---

## ⚙️ Functional Requirements
### 1. กลุ่มสิทธิ์ (`res.groups`)
สร้างกลุ่มใหม่ชื่อ `Validate Privileged`  
ให้เฉพาะผู้ใช้ที่มีสิทธิ์ Validate / Post เอกสารได้

### 2. ฝั่ง UI
- ปุ่ม Validate / Post ต้องเพิ่ม attribute `groups="buz_validate_control.group_validate_privileged"`
- ผู้ใช้ที่ไม่ได้อยู่ในกลุ่มนี้จะ **ไม่เห็นปุ่มเลย**

### 3. ฝั่ง Server (Security Layer)
- Override method:
  - `button_validate()` ของ `stock.picking`
  - `action_post()` ของ `account.move`
- เช็ค `if not self.env.user.has_group('buz_validate_control.group_validate_privileged')`
- ถ้าไม่ผ่าน ให้ raise `AccessError`

---

## 📁 File Structure