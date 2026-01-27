# BUZ Account Receipt - Installation & Upgrade Guide

## Quick Start

### For New Installations

1. **Install the module**:
   ```bash
   cd /opt/instance1/odoo17
   ./odoo-bin -d your_database -i buz_account_receipt
   ```

2. **Configure settings**:
   - Go to: **Settings → Accounting → Configuration**
   - Scroll to "BUZ Account Receipt Settings"
   - Configure:
     - ☑ Auto-Post Receipts
     - ☑ Enforce Single Currency per Receipt
     - ☑ Allow Outstanding Payment Fallback
     - Select Default Bank Journal (optional)

3. **Verify installation**:
   - Go to: **Accounting → Customers → Receipts**
   - Create a test receipt from invoices

---

## For Existing Installations (Upgrade)

### Step 1: Backup Your Database
```bash
# Create database backup
pg_dump your_database > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Step 2: Backup Module Files
```bash
cd /opt/instance1/odoo17/custom-addons
cp -r buz_account_receipt buz_account_receipt_backup_$(date +%Y%m%d)
```

### Step 3: Update Module Code
The code has already been updated in your repository.

### Step 4: Upgrade Module
```bash
cd /opt/instance1/odoo17
./odoo-bin -d your_database -u buz_account_receipt --stop-after-init
```

### Step 5: Restart Odoo Service
```bash
sudo systemctl restart instance1
```

### Step 6: Verify Upgrade

1. **Check database structure**:
   - New table `account_receipt_payment_rel` should exist
   - New fields on `account.receipt` and `account.receipt.line` should be present

2. **Test functionality**:
   - Create a new receipt from invoices
   - Verify batch payment button works
   - Check payment smart button displays
   - Print a receipt and verify new columns

---

## What's New in v2.0.0

### For Users:
- ✨ **Payment Smart Button**: See all payments linked to a receipt
- ✨ **Improved Report**: New columns showing Paid-to-Date, To Collect, Residual After
- ✨ **Better UX**: Clear labels showing "This Payment" vs "Invoice Total"
- ✨ **Batch Payment**: Easier payment registration directly from receipts

### For Developers:
- 🔧 **RV-Ready Methods**: 4 public helper methods for external modules
- 🔧 **M2M Payment Links**: Proper many-to-many relation between receipts and payments
- 🔧 **Signed Amounts**: Correct handling of refunds using signed fields
- 🔧 **Comprehensive Tests**: 10 test cases covering all scenarios

### For Administrators:
- ⚙️ **Configuration Parameters**: 4 configurable settings in Settings
- ⚙️ **Security**: Proper access control using accounting groups
- ⚙️ **Validations**: Strong constraints preventing data inconsistencies

---

## Configuration Reference

### System Parameters (ir.config_parameter)

| Key | Type | Default | Access |
|-----|------|---------|--------|
| `buz_account_receipt.auto_post_receipts` | boolean | `True` | Settings UI |
| `buz_account_receipt.enforce_single_currency_per_receipt` | boolean | `True` | Settings UI |
| `buz_account_receipt.default_bank_journal_id` | integer | `None` | Settings UI |
| `buz_account_receipt.allow_outstanding_fallback` | boolean | `True` | Settings UI |

### Access via Settings UI:
**Settings → Accounting → Configuration → BUZ Account Receipt Settings**

### Access via Technical Settings:
**Settings → Technical → Parameters → System Parameters**

---

## Troubleshooting

### Issue: Module upgrade fails

**Solution**:
```bash
# Check for errors in log
tail -f /var/log/odoo/instance1.log

# Try upgrading with debug mode
./odoo-bin -d your_database -u buz_account_receipt --log-level=debug --stop-after-init
```

### Issue: Payment smart button doesn't show

**Solution**:
- Clear browser cache
- Refresh the form view (F5)
- Check if `payment_count` field is computed correctly

### Issue: Report shows wrong columns

**Solution**:
- Update the report template:
  ```bash
  ./odoo-bin -d your_database -u buz_account_receipt --stop-after-init
  ```
- Clear Odoo assets cache:
  **Settings → Technical → Database Structure → Assets → Clear Cache**

### Issue: Currency validation error

**Solution**:
- Check if `enforce_single_currency_per_receipt` is enabled
- Disable it if you need multi-currency receipts:
  **Settings → Accounting → BUZ Account Receipt Settings → Uncheck "Enforce Single Currency"**

### Issue: Batch payment button doesn't work

**Solution**:
- Ensure receipt is in `posted` state
- Check if invoices have residual amounts
- Verify `allow_outstanding_fallback` setting if no residual

---

## Running Unit Tests

### Run all module tests:
```bash
cd /opt/instance1/odoo17
./odoo-bin -d test_database -i buz_account_receipt --test-enable --stop-after-init
```

### Run specific test:
```bash
./odoo-bin -d test_database --test-enable --stop-after-init \
  --test-tags /buz_account_receipt
```

### View test results:
- Check console output for test results
- Look for lines starting with `test_`
- All tests should show `ok`

---

## Migration Path

### From v1.0.0 to v2.0.0

#### Automatic Migrations:
- New M2M table created automatically
- New fields added to existing models
- Existing data preserved

#### Manual Steps Required:
None - upgrade is fully automatic.

#### Data Impact:
- **Existing receipts**: Will continue to work normally
- **Existing payments**: Won't be automatically linked (historical data)
- **New receipts**: Will use new M2M linking system
- **Reports**: Existing receipts will show new columns with computed values

---

## Performance Considerations

### Database Indexes
The following indexes are automatically created:
- `account_receipt_payment_rel`: (`receipt_id`, `payment_id`)
- Related fields use existing invoice indexes

### Large Data Sets
For installations with > 10,000 receipts:
- Recompute stored fields after upgrade:
  ```python
  receipts = env['account.receipt'].search([])
  receipts._compute_payment_count()
  ```

---

## Rollback Procedure

If you need to rollback to v1.0.0:

### Step 1: Restore Database
```bash
psql your_database < backup_YYYYMMDD_HHMMSS.sql
```

### Step 2: Restore Module Files
```bash
cd /opt/instance1/odoo17/custom-addons
rm -rf buz_account_receipt
mv buz_account_receipt_backup_YYYYMMDD buz_account_receipt
```

### Step 3: Restart Odoo
```bash
sudo systemctl restart instance1
```

**Note**: Rollback will lose any receipts or configurations created after upgrade.

---

## Support

For technical support or questions:
- Check `IMPLEMENTATION_SUMMARY.md` for detailed technical documentation
- Review test cases in `tests.py` for usage examples
- Contact: Ball & Manow

## License
LGPL-3

---

**Last Updated**: October 7, 2025  
**Module Version**: 17.0.2.0.0  
**Odoo Version**: 17.0
