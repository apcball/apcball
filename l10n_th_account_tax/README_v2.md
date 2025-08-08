# Thailand WHT Tax System v2.0 for Odoo 17

## 🎯 Overview
ระบบภาษีหัก ณ ที่จ่าย (Withholding Tax) สำหรับ Odoo 17 ที่ใช้ระบบภาษีมาตรฐานของ Odoo แทนการใช้ฟิลด์กำหนดเอง เพื่อความแม่นยำและการบูรณาการที่ดีกว่า

## ✨ New Features in v2.0

### 🏗️ Standard Tax Integration
- ใช้ `account.tax` มาตรฐานของ Odoo 17
- คำนวณภาษีแม่นยำด้วย repartition lines
- บูรณาการเต็มรูปแบบกับระบบบัญชี

### 🤖 Auto WHT Certificate Generation
- สร้างใบหัก ณ ที่จ่ายอัตโนมัติเมื่อชำระเงิน
- ตรวจสอบภาษี WHT และเชื่อมโยงกับ Payment
- รองรับการสร้างหลายใบในครั้งเดียว

### 💡 Enhanced Auto-Fill
- ตรวจสอบ WHT ใน Invoice อัตโนมัติ
- คำนวณยอดหักภาษี ณ ที่จ่าย
- ปรับยอดชำระเงินให้ถูกต้อง

### 🛍️ Product-Level Configuration
- กำหนด WHT Tax ที่ระดับสินค้า
- Default WHT ที่ระดับหมวดสินค้า
- Auto-assignment ตามประเภท

## 📊 Supported WHT Types

| Type | Rate | Usage | Account Code |
|------|------|--------|--------------|
| Service | 3% | การบริการทั่วไป | 21101 |
| Professional | 5% | ค่าวิชาชีพ | 21102 |
| Rental | 5% | ค่าเช่า | 21103 |
| Transport | 1% | ค่าขนส่ง | 21104 |

## 🚀 Quick Start

### 1. Installation
```bash
# 1. Copy module to addons folder
cp -r l10n_th_account_tax /opt/odoo17/custom-addons/

# 2. Update apps list
# Apps → Update Apps List

# 3. Install module
# Apps → Search "Thailand - Accounting Tax" → Install
```

### 2. Configuration
```python
# Product Configuration
Product → Accounting Tab → Withholding Tax
- WHT Tax (Purchase): Select appropriate WHT tax
- WHT Tax (Sale): For sales if applicable

# Category Configuration  
Product Category → Accounting Tab → Default Withholding Tax
- Set default WHT for all products in category
```

### 3. Usage Workflow
```
1. Create Vendor Bill → WHT auto-filled from product
2. Register Payment → WHT amount auto-calculated
3. Post Payment → WHT Certificate auto-generated
4. View Certificate → Payment Form → WHT Certs button
```

## 📁 File Structure
```
l10n_th_account_tax/
├── data/
│   ├── wht_tax_system.xml          # New standard tax records
│   └── withholding_tax_data.xml    # Original data
├── models/
│   ├── account_payment_wht.py      # Auto certificate generation
│   ├── product_wht.py              # Product WHT configuration
│   └── account_move_odoo17.py      # Enhanced move model
├── views/
│   └── wht_tax_system_views.xml    # New system views
├── migrations/
│   └── 1.0.0/post-migration.py     # Migration from v1.0
├── tests/
│   └── test_wht_system.py          # Test suite
├── docs/
│   ├── USER_GUIDE.md               # Detailed user guide
│   └── WHT_NEW_SYSTEM_PLAN.md      # Technical architecture
└── hooks.py                        # Post-installation setup
```

## 🔄 Migration from v1.0

### Automatic Migration
ระบบจะทำการ migrate ข้อมูลอัตโนมัติเมื่ออัปเกรด:

✅ **What gets migrated:**
- Account Move Lines: `wht_tax_id` → `tax_ids`
- Products: Custom WHT fields → `wht_tax_purchase_id`
- Partners: Default WHT → `property_supplier_taxes_id`
- Certificates: Link to payments

### Manual Migration (if needed)
```python
# From Odoo shell
env = api.Environment(cr, SUPERUSER_ID, {})
from odoo.addons.l10n_th_account_tax.migrations.post_migration import run_manual_migration
run_manual_migration(env)
```

## 🧪 Testing

### Run Test Suite
```python
# From Odoo shell
exec(open('addons/l10n_th_account_tax/tests/test_wht_system.py').read())
run_wht_test()
```

### Manual Testing Checklist
- [ ] Create product with WHT tax
- [ ] Create vendor bill with WHT
- [ ] Register payment with auto WHT calculation
- [ ] Verify WHT certificate generation
- [ ] Check accounting entries

## 🔧 Troubleshooting

### Common Issues

**1. WHT Tax ไม่แสดงใน Invoice**
```
Solution: ตรวจสอบ Product มี WHT Tax กำหนดไว้
→ Product Form → Accounting Tab → WHT Tax (Purchase)
```

**2. Payment Amount ไม่ถูกต้อง**
```
Solution: ระบบปรับ Payment Amount อัตโนมัติ
Payment Amount = Invoice Total - WHT Amount
```

**3. WHT Certificate ไม่สร้างอัตโนมัติ**
```
Solution: ตรวจสอบ Payment มี WHT Tax
→ Payment Form → Generate WHT Certificate (manual)
```

**4. Migration ไม่สำเร็จ**
```
Solution: Check logs และรัน manual migration
→ Settings → Technical → Logging
→ Run manual migration script
```

## 📈 Benefits vs v1.0

| Feature | v1.0 (Custom) | v2.0 (Standard) |
|---------|---------------|-----------------|
| Tax Calculation | Custom logic | Odoo standard |
| Performance | Slower | Faster |
| Accuracy | Good | Excellent |
| Integration | Limited | Full |
| Maintenance | High | Low |
| Upgrades | Difficult | Easy |

## 🛠️ Technical Details

### Tax Configuration
```xml
<!-- Example: Service WHT 3% -->
<record id="wht_tax_service_3" model="account.tax">
    <field name="name">WHT Service 3%</field>
    <field name="amount">-3.0</field>  <!-- Negative = Deduction -->
    <field name="type_tax_use">purchase</field>
    <field name="invoice_repartition_line_ids" eval="[
        (0,0,{'repartition_type': 'base', 'tag_ids': [(4, ref('wht_tag_service'))]}),
        (0,0,{'repartition_type': 'tax', 'account_id': ref('wht_payable_account')})
    ]"/>
</record>
```

### Auto Certificate Logic
```python
def _auto_generate_wht_certificates(self):
    """Auto-generate WHT certificates on payment posting"""
    for payment in self:
        if payment.has_wht_tax:
            wht_data = payment._get_wht_tax_data()
            if wht_data:
                cert = payment._create_wht_certificate(wht_data)
                payment.wht_cert_ids = [(4, cert.id)]
```

## 📞 Support

### Documentation
- [User Guide](docs/USER_GUIDE.md) - Detailed usage instructions
- [Technical Guide](docs/WHT_NEW_SYSTEM_PLAN.md) - Architecture details

### Development
- **Version**: 17.0.2.0.0
- **License**: AGPL-3
- **Dependencies**: `account`, `base`, `product`, `l10n_th`

### Issues & Contributions
1. Report issues with detailed logs
2. Include test cases for bugs
3. Follow Odoo coding standards
4. Test with migration scenarios

---

## 🏆 Why Choose v2.0?

### For Users
- ✅ More accurate calculations
- ✅ Better performance  
- ✅ Automatic certificate generation
- ✅ Seamless payment integration

### For Developers
- ✅ Uses Odoo standards
- ✅ Better maintainability
- ✅ Easier customization
- ✅ Future-proof architecture

### For Businesses
- ✅ Compliance with Thai tax law
- ✅ Reduced manual work
- ✅ Better audit trail
- ✅ Scalable solution

**Ready to upgrade? Follow the migration guide and enjoy the new WHT Tax System v2.0! 🚀**
