# การแสดง Orders Pending Approval ตามช่วง Margin ที่มีสิทธิ์

## 🎯 ปัญหาที่แก้ไข

**ก่อนแก้ไข:**
- Approver ที่มีสิทธิ์อนุมัติช่วง margin ต่างกัน (เช่น 1-29% และ 30-100%) เห็น Orders Pending **เหมือนกันทุก orders**
- ทำให้อาจเกิดความสับสนและ approve ผิด order ได้

**หลังแก้ไข:**
- Approver แต่ละคนจะเห็นเฉพาะ **orders ที่อยู่ในช่วง margin ที่ตนมีสิทธิ์อนุมัติ**เท่านั้น
- แสดงข้อมูลช่วง margin และรายชื่อ approvers อย่างชัดเจนใน tree view

---

## 📋 การแก้ไขที่ทำ

### 1. **แก้ไข Search Logic** (`models/sale_order.py`)

**เปลี่ยนจาก:**
```python
# Admin group เห็นทุก orders
if current_user.has_group('buz_margin_approval.group_margin_approval'):
    return [('approval_state', '=', 'pending')]
```

**เป็น:**
```python
# ทุกคนเห็นเฉพาะ orders ที่อยู่ใน margin_approval_user_ids เท่านั้น
return [
    ('approval_state', '=', 'pending'),
    ('margin_approval_user_ids', 'in', current_user.id)
]
```

**ผลลัพธ์:**
- ✅ Approver จะเห็นเฉพาะ orders ที่มี margin อยู่ในช่วงที่ตนรับผิดชอบ
- ✅ ป้องกันการ approve ผิด order

---

### 2. **เพิ่ม name_get Method** (`models/margin_approval_rule.py`)

เพิ่มการแสดงชื่อช่วง margin อย่างชัดเจน:

```python
def name_get(self):
    """แสดงช่วง margin และรายชื่อ approvers"""
    name = "%.1f%% - %.1f%%" % (line.min_margin, line.max_margin)
    if line.approver_ids:
        approver_names = ', '.join(line.approver_ids.mapped('name')[:2])
        if len(line.approver_ids) > 2:
            approver_names += ', ...'
        name += " (%s)" % approver_names
    return name
```

**ตัวอย่างการแสดงผล:**
- `0.0% - 29.9% (John Doe, Jane Smith)`
- `30.0% - 100.0% (Manager A, ...)`

---

### 3. **ปรับปรุง Tree View** (`views/pending_approval_views.xml`)

สร้าง tree view แบบกำหนดเองสำหรับ Pending Approvals:

**คอลัมน์ที่แสดง:**
- Order Number
- Order Date
- Customer
- Salesperson
- Total Amount
- Margin Amount
- **Margin %** (เปอร์เซ็นต์)
- **Margin Range** (ช่วง เช่น 10.0% - 20.0%)
- **Can Approve** (รายชื่อผู้ที่สามารถ approve ได้)
- **Approval Type** (Any/All)
- **Approved By** (สำหรับ type "All" - แสดงว่าใครอนุมัติไปแล้วบ้าง)

---

## 🔍 ตัวอย่างการใช้งาน

### Scenario: มี 2 Approvers

**Rule Configuration:**
```
Sales Team A - Margin Control
├─ Line 1: 0% - 29%
│  ├─ Approvers: John, Mary
│  └─ Type: Any
└─ Line 2: 30% - 100%
   ├─ Approvers: Manager A, Manager B
   └─ Type: Any
```

**Orders ที่รออนุมัติ:**
- Order SO001: margin = 15% → อยู่ในช่วง 0-29%
- Order SO002: margin = 50% → อยู่ในช่วง 30-100%

**ผลลัพธ์:**
| User | เห็น Orders |
|------|-------------|
| John | SO001 เท่านั้น |
| Mary | SO001 เท่านั้น |
| Manager A | SO002 เท่านั้น |
| Manager B | SO002 เท่านั้น |

---

## ✅ ข้อดีของการแก้ไข

1. **ป้องกันความผิดพลาด**
   - Approver ไม่เห็น orders ที่ไม่มีสิทธิ์อนุมัติ
   - ลดความสับสนและการ approve ผิด order

2. **ข้อมูลชัดเจน**
   - แสดงช่วง margin และรายชื่อ approvers
   - เห็นได้ทันทีว่าใครสามารถ approve order นี้ได้บ้าง

3. **ความปลอดภัย**
   - แม้จะมี group admin ก็ยังเห็นเฉพาะ orders ที่อยู่ในช่วงที่ตนถูกกำหนดเท่านั้น
   - ต้องถูกระบุเป็น approver ในช่วง margin นั้นๆ จึงจะเห็น order

4. **Audit Trail**
   - สำหรับ approval type "All" จะเห็นได้ว่าใครอนุมัติไปแล้วบ้าง
   - ติดตามได้ว่าขาดการอนุมัติจากใครอีก

---

## 🚀 การ Upgrade Module

หลังจากแก้ไขโค้ดแล้ว ให้ทำการ upgrade module:

### วิธีที่ 1: ผ่าน UI
1. ไปที่ **Settings → Apps**
2. ค้นหา **buz Sales Margin Approval**
3. คลิก **Upgrade**

### วิธีที่ 2: ผ่าน Command Line
```bash
cd /opt/instance1/odoo17
./odoo-bin -c odoo.conf -d odoo17 -u buz_margin_approval --stop-after-init
sudo systemctl restart instance1
```

---

## 📝 หมายเหตุ

- Field `margin_approval_user_ids` ถูก compute จาก `margin_rule_line_id` ที่ตรงกับ `margin_percentage` ของแต่ละ order
- เมื่อมีการเปลี่ยนแปลงราคา/ส่วนลด margin จะถูกคำนวณใหม่ และ `margin_approval_user_ids` จะถูก update อัตโนมัติ
- การแสดงผลใน "Orders Pending Approval" จะถูก filter real-time ตาม user ที่ login อยู่

---

## 🔄 การทดสอบ

### Test Case 1: Approver ช่วง 0-29%
1. Login ด้วย user ที่เป็น approver ของช่วง 0-29%
2. ไปที่ **Sales → Orders → Pending Approvals**
3. ควรเห็นเฉพาะ orders ที่มี margin 0-29% เท่านั้น

### Test Case 2: Approver ช่วง 30-100%
1. Login ด้วย user ที่เป็น approver ของช่วง 30-100%
2. ไปที่ **Sales → Orders → Pending Approvals**
3. ควรเห็นเฉพาะ orders ที่มี margin 30-100% เท่านั้น

### Test Case 3: Approver หลายช่วง
1. ถ้า user ถูกกำหนดเป็น approver ใน 2 ช่วง (0-29% และ 30-100%)
2. จะเห็น orders ทั้ง 2 ช่วงที่ตนมีสิทธิ์

---

## 📞 Support

หากมีปัญหาหรือข้อสงสัย กรุณาติดต่อทีม IT
