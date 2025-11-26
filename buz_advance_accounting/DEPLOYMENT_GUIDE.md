# Deployment Guide: GIT & FX Difference JE Module

## Overview

This guide provides step-by-step instructions for deploying the implemented Goods-in-Transit (GIT) and FX Difference Journal Entry logic to your Odoo 17 environment.

---

## Pre-Deployment Checklist

### System Requirements
- Odoo 17 installed and running
- Database with purchase, account, and stock modules installed
- Write access to `/custom-addons` directory
- Backup of production database (critical!)

### Required Modules
- ✅ `purchase` - For purchase orders
- ✅ `account` - For journal entries
- ✅ `stock` - For goods receipt tracking
- ✅ `buz_advance_accounting` - This module (must be installed first)

---

## Installation Steps

### Step 1: Verify Module Files Are in Place

```bash
# Check module structure
ls -la /opt/instance1/odoo17/custom-addons/buz_advance_accounting/

# Should see:
# - models/
# - wizards/
# - tests/
# - views/
# - security/
# - __manifest__.py
# - prompt.md
# - GIT_JE_IMPLEMENTATION_GUIDE.md
# - IMPLEMENTATION_SUMMARY.md
# - QUICK_REFERENCE.md
# - IMPLEMENTATION_CHECKLIST.md
```

### Step 2: Restart Odoo Service

```bash
# Stop Odoo
sudo systemctl stop odoo

# Start Odoo (or use your start command)
sudo systemctl start odoo

# Verify it's running
sudo systemctl status odoo
```

### Step 3: Update Module List in Odoo

In Odoo UI:
1. Go to **Apps** menu
2. Click **Update Apps List** button (or use search)
3. Wait for completion

Or via command line:
```bash
# Update modules in database
cd /opt/instance1/odoo17/
odoo -c odoo.conf -d your_database --update buz_advance_accounting --stop-after-init
```

### Step 4: Install the Module

In Odoo UI:
1. Search for `buz_advance_accounting` in Apps
2. Click on the module
3. Click **Install** button
4. Wait for installation to complete

Monitor the Odoo log:
```bash
tail -f /var/log/odoo/odoo.log | grep -i "buz_advance_accounting"
```

### Step 5: Verify Installation

Check module is installed:
```bash
# In Odoo: Settings → Installed Modules → Search "buz_advance_accounting"
```

Check new tables created:
```sql
-- In database
SELECT * FROM pg_tables 
WHERE tablename LIKE '%advance%' 
OR tablename LIKE '%goods_arrival%'
LIMIT 10;

-- Should show:
-- purchase_advance_accrual
-- purchase_goods_arrival_wizard
-- purchase_goods_arrival_preview_line
```

Check access rules:
```sql
SELECT id, name FROM ir_model_access 
WHERE model_id IN (
  SELECT id FROM ir_model 
  WHERE model LIKE '%goods_arrival%'
);
```

---

## System Configuration

### Step 1: Create Required Accounts

Go to **Accounting** → **Chart of Accounts** and create/assign:

**1. Goods in Transit Account**
- Name: Goods in Transit
- Code: 1031 (or your convention)
- Type: Asset - Current
- Currency: Multi-currency enabled

**2. Foreign AP Trade Account**
- Name: Foreign Accounts Payable - Trade
- Code: 2111 (or your convention)
- Type: Liability - Current
- Currency: Multi-currency enabled

**3. Inventory Account** (if not exists)
- Name: Inventory
- Code: 1110
- Type: Asset - Current

**4. Exchange Rate Difference Account**
- Name: Exchange Rate Difference
- Code: 5100 (or your convention)
- Type: Income or Expense (depending on accounting policy)
- Should be neutral account or loss/gain account

### Step 2: Set Exchange Rate Difference Account in Config

Go to **Advance Accounting** → **Configuration** (or search for "Advance Accounting Config"):

1. Select your company
2. Set **Exchange Rate Difference Account** to the account created in step 4
3. Save

```sql
-- Verify in database
SELECT company_id, exchange_rate_diff_account_id 
FROM advance_accounting_config;
```

### Step 3: Set Up Exchange Rates

Go to **Accounting** → **Settings** → **Currencies** or **Accounting** → **Configuration** → **Currency Rates**

Add exchange rates for:
- Bill date (e.g., Jan 1, 2025)
- Arrival date (e.g., Jan 15, 2025)

Example for USD to THB:
```
Date: 2025-01-01, USD → THB: 35.00
Date: 2025-01-15, USD → THB: 36.00
```

Verify rates:
```sql
SELECT id, name, rate, currency_id 
FROM res_currency_rate 
WHERE currency_id = (SELECT id FROM res_currency WHERE name = 'USD');
```

### Step 4: Set Company Currency

Go to **Settings** → **Companies** → Your Company:
- Company Name: Your Company
- Currency: THB (or your base currency)
- Ensure it's set correctly

---

## Testing the Implementation

### Pre-Test Verification

```bash
# 1. Check module is loaded
grep -i "buz_advance_accounting" /var/log/odoo/odoo.log | tail -5

# 2. Verify models exist
grep "model = 'purchase.advance.accrual'" /var/log/odoo/odoo.log

# 3. Check for errors
grep -i "error\|exception" /var/log/odoo/odoo.log | tail -10
```

### Test 1: Create Purchase Order

1. Go to **Purchases** → **Purchase Orders**
2. Create new PO:
   - Vendor: Select foreign vendor (USD currency)
   - Product: Add any product
   - Unit Price: 100
   - Quantity: 100 (total 10,000 USD)
3. Confirm PO
4. Verify it's confirmed state

### Test 2: Post GIT Entry

1. Open the PO
2. Create advance accrual entry (using existing wizard)
3. Set date to bill date (e.g., Jan 1)
4. Set amount to 10,000 USD
5. Post the entry
6. Verify journal entry is posted with correct amounts

### Test 3: Post Goods Arrival Entry

1. Open the PO
2. Create stock picking
3. Receive goods
4. Click **Goods Arrival Reclassification** action
5. Select the GIT accrual entry
6. Set arrival date (e.g., Jan 15)
7. Select accounts
8. Review preview
9. Click **Post Goods Arrival Entry**
10. Verify arrival journal entry is posted

### Test 4: Verify GL Entries

Check accounting transactions:
```sql
-- GL entries for GIT account
SELECT date, name, debit, credit 
FROM account_move_line 
WHERE account_id = (SELECT id FROM account_account WHERE code = '1031')
ORDER BY date;

-- GL entries for FX difference account
SELECT date, name, debit, credit 
FROM account_move_line 
WHERE account_id = (SELECT id FROM account_account WHERE code = '5100')
ORDER BY date;
```

---

## Run Automated Tests

### Option 1: Using pytest (Recommended)

```bash
# Navigate to module directory
cd /opt/instance1/odoo17/custom-addons/buz_advance_accounting

# Run all tests
pytest tests/test_goods_in_transit_je.py -v

# Run specific test
pytest tests/test_goods_in_transit_je.py::TestGoodsInTransitJELogic::test_01_post_git_entry -v

# Run with coverage
pytest tests/test_goods_in_transit_je.py --cov=. -v
```

### Option 2: Using Odoo Test Command

```bash
cd /opt/instance1/odoo17/

# Run module tests
odoo -c odoo.conf -d your_database \
  --test-tags=buz_advance_accounting \
  --stop-after-init -l test
```

### Expected Test Results

```
test_01_post_git_entry ............................ PASSED ✓
test_02_post_goods_arrival_entry_with_fx_gain .... PASSED ✓
test_03_post_goods_arrival_entry_with_fx_loss .... PASSED ✓
test_04_complete_workflow ......................... PASSED ✓

======================== 4 passed in X.XXs ========================
```

---

## Verification Checklist

After installation and testing:

### Module Installation
- [ ] Module appears in installed modules list
- [ ] No errors in Odoo log during installation
- [ ] All database tables created
- [ ] Access control rules added

### Models & Fields
- [ ] `purchase.advance.accrual` has new fields
- [ ] `stock.picking` has new methods
- [ ] Wizard models created and accessible

### UI Components
- [ ] Goods Arrival Wizard appears in actions
- [ ] Forms display correctly
- [ ] No JavaScript errors in console

### Configuration
- [ ] Accounts are created and configured
- [ ] Exchange Rate Difference account set in config
- [ ] Exchange rates are available in system

### Functionality
- [ ] Can create GIT accrual entries
- [ ] Can post GIT journal entries
- [ ] Can post goods arrival entries
- [ ] FX difference calculated correctly
- [ ] Journal entries balanced (DR = CR)

### Data Integrity
- [ ] All amounts stored correctly
- [ ] FX rates saved for audit
- [ ] State transitions work properly
- [ ] Links between entries maintained

---

## Troubleshooting

### Issue: Module Not Appearing in App List

**Solution:**
```bash
# 1. Restart Odoo
sudo systemctl restart odoo

# 2. Update module list again
# In Odoo: Apps → Update Apps List

# 3. Check Odoo log
tail -100 /var/log/odoo/odoo.log | grep -i "error"

# 4. Check file permissions
ls -l /opt/instance1/odoo17/custom-addons/buz_advance_accounting/__manifest__.py
# Should be readable
```

### Issue: "Exchange Rate Difference Account is not configured"

**Solution:**
1. Go to **Advance Accounting** → **Configuration**
2. Select your company
3. Set the **Exchange Rate Difference Account** field
4. Save

Or via database:
```sql
UPDATE advance_accounting_config 
SET exchange_rate_diff_account_id = (SELECT id FROM account_account WHERE code = '5100')
WHERE company_id = 1;
```

### Issue: No Exchange Rate Found for Date

**Solution:**
1. Go to **Accounting** → **Configuration** → **Currency Rates**
2. Create/update exchange rate for the date:
   - Date: The date you need
   - From Currency: USD (or source)
   - To Currency: THB (or target)
   - Rate: Correct exchange rate
3. Save

Or via database:
```sql
INSERT INTO res_currency_rate (name, rate, currency_id, company_id)
VALUES ('2025-01-01', 0.030857, 4, 1);  -- 1 USD = 35 THB
```

### Issue: Wizard Not Opening from Stock Picking

**Solution:**
1. Verify picking is linked to a PO:
   - Stock Picking → Purchase Order field should show PO
2. Verify GIT accrual exists for that PO:
   - Open PO → Advance Accruals tab
3. Check access rights:
   - User → Groups → Should have purchase/accounting access
4. Clear browser cache and refresh

---

## Rollback Plan (If Needed)

### Option 1: Remove Module

```bash
# In Odoo UI
Apps → Search "buz_advance_accounting" → Click → Uninstall

# Or via command line
cd /opt/instance1/odoo17/
odoo -c odoo.conf -d your_database \
  --uninstall buz_advance_accounting \
  --stop-after-init
```

### Option 2: Database Rollback

```bash
# If you have a backup from before installation
sudo pg_restore -U odoo -d your_database /path/to/backup.sql

# Or if using auto-backup
psql -U odoo -d your_database -c "
  DROP TABLE IF EXISTS purchase_advance_accrual CASCADE;
  DROP TABLE IF EXISTS purchase_goods_arrival_wizard CASCADE;
  DROP TABLE IF EXISTS purchase_goods_arrival_preview_line CASCADE;
"
```

---

## Post-Deployment Verification

### Week 1: Initial Testing
- [ ] Run all automated tests
- [ ] Manually test complete workflow
- [ ] Verify GL entries match expectations
- [ ] Check FX calculations with manual calculation

### Week 2-4: Monitoring
- [ ] Monitor Odoo logs for errors
- [ ] Check database backup succeeds
- [ ] Monitor system performance
- [ ] Collect user feedback

### Month 1: Full Review
- [ ] Review all GL entries created
- [ ] Reconcile with vendor statements
- [ ] Validate FX calculations across all entries
- [ ] Document any issues or enhancements needed

---

## Support & Maintenance

### Getting Help

1. **Check Documentation:**
   - GIT_JE_IMPLEMENTATION_GUIDE.md
   - QUICK_REFERENCE.md
   - IMPLEMENTATION_SUMMARY.md

2. **Review Test Cases:**
   - tests/test_goods_in_transit_je.py

3. **Check Code Comments:**
   - models/advance_accrual.py
   - wizards/goods_arrival_wizard.py

### Maintenance Tasks

**Monthly:**
- Check for Odoo security updates
- Verify exchange rates are current
- Spot check GL entries for accuracy

**Quarterly:**
- Review FX difference amounts for trends
- Validate system still functioning correctly
- Run automated test suite

**Annually:**
- Review system performance
- Plan for enhancements
- Update documentation as needed

---

## Success Criteria

Deployment is successful when:

✅ Module installs without errors  
✅ All automated tests pass  
✅ Manual workflow tests succeed  
✅ GIT entries post with correct amounts  
✅ Arrival entries calculate FX difference correctly  
✅ GL entries are balanced  
✅ System performs acceptably  
✅ Users report satisfaction  

---

## Contact & Support

For issues or questions:
1. Review documentation in module directory
2. Check test cases for working examples
3. Review code comments for implementation details
4. Consult Odoo documentation for general features

**Documentation Files:**
- GIT_JE_IMPLEMENTATION_GUIDE.md - Technical details
- QUICK_REFERENCE.md - Quick lookup
- IMPLEMENTATION_SUMMARY.md - Feature overview
- IMPLEMENTATION_CHECKLIST.md - Verification checklist
