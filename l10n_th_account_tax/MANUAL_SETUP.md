# Manual WHT Setup Guide (Wizard Temporarily Disabled)
# คู่มือการตั้งค่า WHT แบบ Manual

## Problem / ปัญหา
The WHT Setup Wizard is temporarily disabled due to field validation issues in Odoo 17. Use this manual setup instead.

WHT Setup Wizard ถูกปิดใช้งานชั่วคราวเนื่องจาก field validation issues ใน Odoo 17 ให้ใช้การตั้งค่าแบบ manual แทน

## Manual Setup Steps / ขั้นตอนการตั้งค่าแบบ Manual

### Step 1: Create WHT Account / สร้าง Account สำหรับ WHT

1. Go to **Accounting → Configuration → Chart of Accounts**
   ไปที่ **บัญชี → การตั้งค่า → ผังบัญชี**

2. Click **Create** to add new account / คลิก **สร้าง** เพื่อเพิ่มบัญชีใหม่:
   - **Account Name / ชื่อบัญชี**: "Withholding Tax Payable" หรือ "ภาษีหัก ณ ที่จ่าย ค้างจ่าย"
   - **Code / รหัส**: "2131" (หรือรหัสที่ว่าง)
   - **Type / ประเภท**: "Current Liabilities" หรือ "หนี้สินหมุนเวียน"
   - **Account Type**: เลือก "Payable" หรือ "Current Liabilities"

3. After saving, edit the account again and check **"WHT Account"** field
   หลังจาก save แล้ว ให้ edit account อีกครั้งและเช็ค **"WHT Account"** field

4. Save the account / บันทึกบัญชี

### Step 2: Create WHT Tax Types / สร้างประเภทภาษีหัก ณ ที่จ่าย

1. Go to **Accounting → Configuration → Accounting → Withholding Tax**
   ไปที่ **บัญชี → การตั้งค่า → บัญชี → ภาษีหัก ณ ที่จ่าย**

2. Create **Service WHT 3%** / สร้าง **ภาษีหัก ณ ที่จ่าย ค่าบริการ 3%**:
   - **Name / ชื่อ**: "Service WHT 3%" หรือ "ภาษีหัก ณ ที่จ่าย ค่าบริการ 3%"
   - **Account / บัญชี**: Select the WHT account created in Step 1
   - **Percent / เปอร์เซ็นต์**: 3.00
   - **Personal Income Tax**: No (unchecked) / ไม่เช็ค
   - **Income Tax Form**: PND3
   - **Type of Income / ประเภทรายได้**: Service

3. Create **Rental WHT 5%** / สร้าง **ภาษีหัก ณ ที่จ่าย ค่าเช่า 5%** (optional):
   - **Name / ชื่อ**: "Rental WHT 5%" หรือ "ภาษีหัก ณ ที่จ่าย ค่าเช่า 5%"
   - **Account / บัญชี**: Select the WHT account created in Step 1
   - **Percent / เปอร์เซ็นต์**: 5.00
   - **Personal Income Tax**: No (unchecked) / ไม่เช็ค
   - **Income Tax Form**: PND3
   - **Type of Income / ประเภทรายได้**: Rental

4. Create **Personal Income Tax** / สร้าง **ภาษีเงินได้บุคคลธรรมดา** (optional):
   - **Name / ชื่อ**: "Personal Income Tax" หรือ "ภาษีเงินได้บุคคลธรรมดา"
   - **Account / บัญชี**: Select the WHT account created in Step 1
   - **Percent / เปอร์เซ็นต์**: 0.00 (variable rate / อัตราแปรผัน)
   - **Personal Income Tax**: Yes (checked) / เช็ค
   - **Income Tax Form**: PND1
   - **Type of Income / ประเภทรายได้**: Salary

### Step 3: Configure Products

For each product that requires WHT:

1. Go to **Products**
2. Edit the product
3. In **General Information** tab:
   - Set **Withholding Tax** field (for customer invoices)
4. In **Purchase** tab:
   - Set **Supplier Individual WHT Tax** (for individual vendors)
   - Set **Supplier Company WHT Tax** (for company vendors)

### Step 4: Test WHT Workflow

1. **Create Vendor Bill**:
   - Add product with WHT tax configured
   - Verify WHT fields appear in invoice lines
   - Confirm the bill

2. **Register Payment**:
   - Click "Register Payment" on the bill
   - Verify WHT amount is calculated and deducted
   - Check that writeoff account is set to WHT account
   - Confirm payment

3. **Verify Results**:
   - Check journal entries created
   - Verify WHT certificate is generated (if configured)

## Verification Checklist

- [ ] WHT account created and marked as "WHT Account"
- [ ] At least one WHT tax type created with proper account
- [ ] Products configured with appropriate WHT taxes
- [ ] Test invoice with WHT calculation working
- [ ] Test payment with WHT deduction working

## Common Issues

### Issue: "WHT Account" field not visible
**Solution**: Make sure you have "Show Full Accounting Features" enabled in user settings.

### Issue: WHT fields not showing in invoice lines
**Solution**: Ensure products have WHT taxes assigned and user has proper permissions.

### Issue: Payment not deducting WHT
**Solution**: 
1. Verify invoice lines have WHT tax assigned
2. Check "Group Payment" option in payment wizard
3. Ensure WHT tax has proper account configured

## Re-enabling the Wizard

Once the base WHT functionality is working, the wizard can be re-enabled by:

1. Uncommenting lines in `__manifest__.py`
2. Uncommenting lines in `wizard/__init__.py`
3. Uncommenting lines in `security/ir.model.access.csv`
4. Upgrading the module

The wizard was temporarily disabled to resolve field validation issues and allow the core WHT functionality to work properly.
