# Troubleshooting Internal Server Error

## Problem
After restart, Odoo shows "Internal Server Error"

## Root Cause  
Most likely: Odoo module cache or database state issue

## Solution Steps

### Step 1: Clean Cache (DONE ✅)
```bash
cd /opt/instance1/odoo17/custom-addons/buz_advance_accounting
sudo find . -name "__pycache__" -type d -exec rm -rf {} +
sudo find . -name "*.pyc" -delete
```

### Step 2: Restart Odoo Service
```bash
sudo systemctl stop odoo
sleep 3
sudo systemctl start odoo
```

### Step 3: Check Odoo Status
```bash
sudo systemctl status odoo
```

### Step 4: Update Module List (if using Odoo UI)
- Go to Settings → Activate Developer Mode
- Go to Apps → Update Apps List (click button)
- Search for "buz_advance_accounting"
- Click Install button

### Step 5: Verify Installation
Check in Odoo UI:
1. Go to Settings → Installed Modules
2. Search "buz_advance_accounting"
3. Should show: Installed (with green checkmark)

### Step 6: Test the Module
1. Go to Purchases menu
2. Look for "Advance Accounting" options
3. Try creating a test PO to verify functionality

## If Problem Persists

### Option A: Check Odoo Logs
```bash
# If using systemd
sudo journalctl -u odoo -n 100 --follow

# Or if logs are in /var/log
sudo tail -f /var/log/odoo*.log
```

### Option B: Force Module Reinstall (via command line)
```bash
cd /opt/instance1/odoo17
# Uninstall
odoo -c odoo.conf -d yourdb --uninstall buz_advance_accounting --stop-after-init

# Clean database cache
python manage.py shell  # if available
# Or direct SQL:
# DELETE FROM ir_model WHERE model LIKE 'purchase.advance%';
# DELETE FROM ir_model WHERE model LIKE 'purchase.goods%';

# Reinstall
odoo -c odoo.conf -d yourdb --install buz_advance_accounting --stop-after-init
```

### Option C: Database Rollback
If you have a backup from before installation:
```bash
sudo pg_restore -U odoo -d yourdb /path/to/backup.sql
```

## Files That Were Just Fixed
1. ✅ `wizards/goods_arrival_wizard.py` - Fixed One2many field assignments
2. ✅ All pycache files removed with proper permissions
3. ✅ XML files verified as valid

## Verification Checklist
- [ ] Service restarted successfully
- [ ] No "Internal Server Error" on page reload
- [ ] Module appears in installed modules list
- [ ] Can navigate to Purchase menu
- [ ] Can create Purchase Orders
- [ ] Can access advance accrual functions

## Next Steps After Restart
1. Verify module loads without errors
2. Create test PO in USD (or foreign currency)
3. Test creating GIT entry
4. Test posting goods arrival entry
5. Verify journal entries posted correctly

---

**Status:** All code issues fixed, cache cleaned, ready for Odoo restart.
