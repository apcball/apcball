# Admin Group Guide - Sales Margin Approval

## 🎯 ภาพรวม

Module นี้มี **3 Security Groups** หลัก:

### 1. **Sales Margin Approver User** (`group_sales_margin_approver_user`)
- พนักงานขายที่ต้องใช้ "Confirm To SO" flow
- ไม่สามารถกด "Confirm Sale" โดยตรง

### 2. **Sales Margin Approvers** (`group_margin_approval`)
- ผู้อนุมัติทั่วไป
- เห็นเฉพาะ **orders ที่อยู่ในช่วง margin ที่ตนถูกกำหนด**
- ต้องถูกระบุใน "Margin Approval Rule Line" เป็น approver

### 3. **Sales Margin Approval Admin** (`group_margin_approval_admin`) ⭐ **ใหม่!**
- **ผู้ดูแลระบบ/Admin**
- เห็น **ทุก orders ที่ pending approval** โดยไม่ถูกจำกัดด้วยช่วง margin
- สามารถ approve ได้ทุก orders
- มี implied group: `Sales Margin Approvers`

---

## 📊 ตารางเปรียบเทียบ

| คุณสมบัติ | Regular Approver | Admin Group |
|----------|-----------------|-------------|
| เห็น orders ตามช่วง margin ที่กำหนด | ✅ ใช่ | ❌ ไม่ จำกัด |
| เห็นทุก orders pending | ❌ ไม่ | ✅ ใช่ |
| ต้องถูกระบุใน Rule Line | ✅ ใช่ | ❌ ไม่ |
| สามารถ approve ได้ | ✅ ใช่ | ✅ ใช่ |
| Implied Groups | Sales Margin Approvers | Sales Margin Approvers |

---

## 🔧 การตั้งค่า Admin Group

### วิธีที่ 1: ผ่าน UI

1. ไปที่ **Settings → Users & Companies → Users**
2. เลือก user ที่ต้องการเป็น Admin
3. ไปที่แท็บ **Access Rights**
4. ในหมวด **Sales**:
   - เลือก ✅ **Sales Margin Approval Admin**
5. คลิก **Save**

### วิธีที่ 2: ผ่าน Groups Management

1. ไปที่ **Settings → Users & Companies → Groups**
2. ค้นหา **"Sales Margin Approval Admin"**
3. เปิด group นั้น
4. ในแท็บ **Users** เพิ่ม users ที่ต้องการ
5. คลิก **Save**

---

## 💡 Use Cases

### Scenario 1: Finance Manager ต้องเห็นทุก orders

**ปัญหา:**
- Finance Manager ต้องการดูภาพรวม orders ทั้งหมดที่รออนุมัติ
- แต่ไม่ถูกระบุเป็น approver ในทุกช่วง margin

**วิธีแก้:**
```
1. เพิ่ม Finance Manager เข้า group "Sales Margin Approval Admin"
2. Finance Manager จะเห็นทุก orders pending โดยอัตโนมัติ
3. สามารถ approve ได้ทุก orders
```

### Scenario 2: Approver ทั่วไปเห็นเฉพาะช่วงของตน

**Setup:**
```
Rule: Sales Team Margin Control
├─ Line 1: 0% - 29%
│  └─ Approvers: [John]
└─ Line 2: 30% - 100%
   └─ Approvers: [Manager A]
```

**ผลลัพธ์:**

| User | Group | เห็น Orders |
|------|-------|------------|
| John | Sales Margin Approvers | เฉพาะ margin 0-29% |
| Manager A | Sales Margin Approvers | เฉพาะ margin 30-100% |
| CEO | Sales Margin Approval Admin | **ทุก orders** |

### Scenario 3: Backup Approver

**สถานการณ์:**
- Approver หลักลาพัก
- ต้องมีคนสำรองที่สามารถ approve แทนได้

**วิธีแก้:**
```
เพิ่ม Backup Approver เข้า group "Sales Margin Approval Admin"
→ สามารถ approve แทนได้ทุก orders โดยไม่ต้องแก้ไข rule
```

---

## 🔐 Security Considerations

### ข้อควรระวัง

1. **จำกัดจำนวน Admin**
   - ให้เฉพาะผู้ที่จำเป็นจริงๆ
   - เช่น: Finance Manager, Director, CEO

2. **Audit Trail**
   - ทุกการ approve จะถูกบันทึกใน chatter
   - ระบุชื่อผู้ approve และเวลา

3. **Separation of Duties**
   - ควรแยก Admin กับ Sales Users
   - Sales Users ไม่ควรมี Admin rights

### Best Practices

✅ **ควรทำ:**
- เพิ่ม 2-3 คนเป็น Admin (สำหรับสำรอง)
- มี Finance หรือ Management level เป็น Admin
- Review admin list เป็นประจำทุก quarter

❌ **ไม่ควรทำ:**
- ให้ Sales Users เป็น Admin
- ให้หลายคนเกินไปเป็น Admin
- ลืม revoke admin rights เมื่อคนลาออก

---

## 🚀 การทดสอบ

### Test Case 1: Admin เห็นทุก orders

**Steps:**
1. Login ด้วย user ที่เป็น Admin
2. ไปที่ **Sales → Orders → Pending Approvals**
3. ควรเห็น **ทุก orders** ที่มี approval_state = 'pending'
4. ไม่ว่า margin จะเป็นช่วงไหน

**Expected Result:**
```
✅ เห็น orders margin 5%
✅ เห็น orders margin 25%
✅ เห็น orders margin 50%
✅ เห็น orders margin 95%
```

### Test Case 2: Regular Approver เห็นเฉพาะช่วงของตน

**Setup:**
- User "John" เป็น approver ของช่วง 0-29%
- John **ไม่ได้** อยู่ใน Admin group

**Steps:**
1. Login ด้วย John
2. ไปที่ **Sales → Orders → Pending Approvals**

**Expected Result:**
```
✅ เห็น orders margin 5%
✅ เห็น orders margin 25%
❌ ไม่เห็น orders margin 50%
❌ ไม่เห็น orders margin 95%
```

### Test Case 3: Admin สามารถ approve ได้

**Steps:**
1. Login ด้วย Admin
2. เปิด order ที่ pending (margin 85%)
3. คลิก **"Approve Margin"**

**Expected Result:**
```
✅ สามารถ approve ได้ (แม้จะไม่ได้ถูกระบุใน rule line)
✅ บันทึก approval ใน chatter
✅ Order state เปลี่ยนเป็น 'approved'
```

---

## 📝 Technical Details

### Code Reference

**File:** `models/sale_order.py`

```python
def _search_can_current_user_approve(self, operator, value):
    current_user = self.env.user
    
    # Admin group can see ALL pending orders
    if current_user.has_group('buz_margin_approval.group_margin_approval_admin'):
        return [('approval_state', '=', 'pending')]
    
    # Regular approvers: filtered by margin_approval_user_ids
    return [
        ('approval_state', '=', 'pending'),
        ('margin_approval_user_ids', 'in', current_user.id)
    ]
```

### Security XML

**File:** `security/margin_approval_security.xml`

```xml
<record id="group_margin_approval_admin" model="res.groups">
    <field name="name">Sales Margin Approval Admin</field>
    <field name="implied_ids" eval="[(4, ref('group_margin_approval'))]"/>
    <field name="comment">Administrators who can see and approve all pending orders</field>
</record>
```

---

## 🔄 Upgrade Instructions

หลังจากเพิ่ม admin group แล้ว ต้อง upgrade module:

### วิธีที่ 1: Command Line
```bash
cd /opt/instance1/odoo17
./odoo-bin -c odoo.conf -d odoo17 -u buz_margin_approval --stop-after-init
sudo systemctl restart instance1
```

### วิธีที่ 2: UI
1. ไปที่ **Settings → Apps**
2. ค้นหา **"buz Sales Margin Approval"**
3. คลิก **Upgrade**
4. รอให้ upgrade เสร็จ

---

## ❓ FAQ

**Q: Admin group จำเป็นต้องถูกระบุใน Margin Rule Line หรือไม่?**
A: ไม่จำเป็น Admin เห็นและ approve ได้ทุก orders โดยอัตโนมัติ

**Q: ถ้าลบ user ออกจาก admin group จะเกิดอะไร?**
A: User จะกลายเป็น regular approver เห็นเฉพาะ orders ที่ตนถูกระบุใน rule line

**Q: Admin group สามารถข้าม "Confirm To SO" flow ได้หรือไม่?**
A: ไม่ได้ Admin ยังคงต้องปฏิบัติตาม confirmation flow ตามปกติ

**Q: มีข้อจำกัดจำนวน admin หรือไม่?**
A: ไม่มี แต่ recommend ให้มี 2-5 คนเพื่อความปลอดภัย

**Q: Admin สามารถแก้ไข Margin Rule ได้หรือไม่?**
A: ได้ ถ้ามี access rights ที่เหมาะสม (ดูที่ ir.model.access.csv)

---

## 📞 Support

หากมีคำถามหรือปัญหาเกี่ยวกับ admin group:
- ติดต่อ IT Support
- ดูเอกสาร: `APPROVAL_BY_MARGIN_RANGE.md`
- ตรวจสอบ logs ที่ Odoo server

---

## 📋 Summary

✨ **Group ใหม่: Sales Margin Approval Admin**
- เห็นทุก orders pending
- Approve ได้ทุก orders
- ไม่ถูกจำกัดด้วยช่วง margin
- เหมาะสำหรับ Management/Finance level
