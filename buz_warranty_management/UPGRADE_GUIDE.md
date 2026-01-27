# Upgrade Guide - RMA Enhanced Features

## Overview

This guide explains how to upgrade the `buz_warranty_management` module from the basic version to the enhanced RMA version.

---

## ⚠️ Important Notes

### Breaking Changes
- **New dependency added:** `stock_account` (standard Odoo module)
- **New statuses added:** Existing claims will remain in their current status
- **New fields added:** Existing claims will have empty claim_line_ids (this is expected)

### Non-Breaking Changes
- All existing functionality is preserved
- Existing warranty cards and claims will continue to work
- Reports are backwards compatible

---

## 📋 Pre-Upgrade Checklist

Before upgrading, ensure:

- ✅ You have a backup of your database
- ✅ Odoo server is running (for upgrade command)
- ✅ You have admin/technical access
- ✅ `stock_account` module is available (it's standard in Odoo)
- ✅ No users are actively working with warranty claims

---

## 🚀 Upgrade Steps

### Step 1: Backup Database

```bash
# Using Odoo's built-in backup
# Go to Database Manager: http://your-server:8069/web/database/manager
# Click "Backup" and download the backup file

# Or using PostgreSQL directly
pg_dump -U odoo your_database > backup_before_rma_upgrade.sql
```

### Step 2: Stop Odoo (Optional but Recommended)

```bash
sudo systemctl stop odoo
# or
sudo service odoo stop
```

### Step 3: Update Module Files

The module files are already updated in:
```
/opt/instance1/odoo17/custom-addons/buz_warranty_management/
```

Verify all new files exist:
```bash
cd /opt/instance1/odoo17/custom-addons/buz_warranty_management
ls -la models/warranty_claim_line.py
ls -la models/res_config_settings.py
ls -la wizard/warranty_rma_receive_wizard.py
ls -la wizard/warranty_replacement_issue_wizard.py
ls -la wizard/warranty_invoice_wizard.py
```

### Step 4: Start Odoo (if stopped)

```bash
sudo systemctl start odoo
# or
sudo service odoo start
```

### Step 5: Upgrade Module via Command Line

```bash
# Navigate to Odoo directory
cd /opt/instance1/odoo17

# Run upgrade command
# Replace 'your_database' with your actual database name
./odoo-bin -u buz_warranty_management -d your_database --stop-after-init

# If you have a custom config file
./odoo-bin -c /etc/odoo.conf -u buz_warranty_management -d your_database --stop-after-init
```

**Note:** The `--stop-after-init` flag will stop Odoo after the upgrade. Remove it if you want Odoo to keep running.

### Step 6: Restart Odoo

```bash
sudo systemctl restart odoo
# or
sudo service odoo restart
```

### Step 7: Clear Browser Cache

- In your browser, clear cache and refresh (Ctrl+Shift+R or Cmd+Shift+R)
- Or use incognito/private mode to test

---

## 🔧 Post-Upgrade Configuration

### Step 1: Login as Admin

Login to Odoo with administrator credentials.

### Step 2: Activate Developer Mode

- Settings → Activate Developer Mode
- Or append `?debug=1` to URL

### Step 3: Verify Module Installation

- Apps → Search "Warranty Management"
- Should show version **17.0.1.0.0** or higher
- Status should be "Installed"

### Step 4: Configure Warranty Settings

**Go to:** Settings → General Settings → Scroll to "Warranty Management"

**Configure Stock Operations:**

1. **RMA IN Picking Type:**
   - Click dropdown
   - Select existing picking type (e.g., "Receipts" or "WH/IN")
   - Or create new: Inventory → Configuration → Operation Types → Create

2. **Repair Location:**
   - Click dropdown
   - Select internal location (e.g., "WH/Stock/Repair")
   - Or create new: Inventory → Configuration → Locations → Create

3. **Replacement OUT Picking Type:**
   - Select outgoing type (e.g., "Delivery Orders" or "WH/OUT")

4. **Scrap Location:**
   - Select scrap location (e.g., "Virtual Locations/Scrap")

**Configure Accounting:**

5. **Warranty Expense Account:**
   - Select expense account from Chart of Accounts
   - Recommended: Create dedicated "Warranty Expense" account (5100 range)
   - Accounting → Configuration → Chart of Accounts → Create if needed

6. **Default Service Product:**
   - Select service product (e.g., "Repair Service")
   - Or create: Products → Create → Type: Service

Click **Save**.

---

## ✅ Verification Tests

### Test 1: Verify New Fields on Claim

1. Go to Warranty → Claims
2. Open any existing claim or create new
3. Verify you see:
   - New button box at top (may be empty if no RMA created)
   - New "Claim Lines" tab in notebook
   - New action buttons: "Create RMA IN", "Issue Replacement"

### Test 2: Verify Settings

1. Settings → General Settings → Warranty Management section
2. Should see two groups:
   - RMA Configuration (4 fields)
   - Accounting Configuration (2 fields)

### Test 3: Test RMA Workflow

1. Create a test warranty claim
2. Click "Create RMA IN"
3. Wizard should open with pre-filled fields
4. Cancel wizard (don't create yet)
5. Click "Issue Replacement"
6. Replacement wizard should open
7. Cancel wizard

### Test 4: Check Security

1. As admin, go to Settings → Users & Companies → Groups
2. Find "Warranty / User" group
3. Click → Access Rights tab
4. Should see new models:
   - warranty.claim.line
   - warranty.rma.receive.wizard
   - warranty.replacement.issue.wizard
   - warranty.invoice.wizard

---

## 🔍 Troubleshooting

### Issue: Module won't upgrade

**Error:** "Module not found" or "No module named..."

**Solution:**
```bash
# Ensure module path is correct
ls /opt/instance1/odoo17/custom-addons/buz_warranty_management

# Check Odoo config for addons_path
grep addons_path /etc/odoo.conf

# Restart Odoo and try again
sudo systemctl restart odoo
```

### Issue: Settings section not visible

**Error:** Can't see "Warranty Management" in Settings

**Solution:**
1. Ensure you're admin user
2. Refresh page (Ctrl+F5)
3. Clear browser cache
4. Check group membership: Settings → Users → Your User → Access Rights

### Issue: "stock_account module not found"

**Error:** Module dependency error

**Solution:**
```bash
# Install stock_account module first
./odoo-bin -i stock_account -d your_database --stop-after-init

# Then upgrade warranty module
./odoo-bin -u buz_warranty_management -d your_database --stop-after-init
```

### Issue: Wizards don't open

**Error:** Button clicks don't open wizards

**Solution:**
1. Check JavaScript console for errors (F12 → Console)
2. Clear browser cache completely
3. Try incognito mode
4. Check if popup blocker is enabled

### Issue: Access denied to claim lines

**Error:** Users can't see claim lines tab

**Solution:**
1. Go to Settings → Users & Companies → Users
2. Select user → Access Rights tab
3. Ensure user has "Warranty / User" or "Warranty / Manager" group
4. If still issues, check: Settings → Technical → Security → Access Rights
5. Search for "warranty.claim.line" and verify rules

---

## 🔄 Rollback Procedure (If Needed)

If you need to rollback to the previous version:

### Option 1: Restore Database Backup

```bash
# Drop current database (CAREFUL!)
psql -U odoo -c "DROP DATABASE your_database;"

# Restore from backup
psql -U odoo -c "CREATE DATABASE your_database;"
psql -U odoo your_database < backup_before_rma_upgrade.sql

# Restart Odoo
sudo systemctl restart odoo
```

### Option 2: Uninstall Module and Reinstall Old Version

**Not recommended** - will lose all warranty data.

---

## 📊 Data Migration Notes

### Existing Warranty Cards
- ✅ No changes required
- ✅ Will continue to work normally
- ✅ Can still generate certificates

### Existing Warranty Claims
- ✅ Will keep current status
- ✅ Can still create out-of-warranty quotations
- ⚠️ Claim lines will be empty (add manually if needed)
- ⚠️ RMA pickings will be empty (new claims only)

### New Workflow Adoption
- New claims can use full RMA features
- Existing claims can optionally use new features
- You can add claim lines to existing claims manually

---

## 🎓 Training Users

After upgrade, brief users on:

1. **New Claim Lines Tab**
   - How to add parts/consumables
   - When to mark "Need Replacement"

2. **RMA IN Process**
   - When to use "Create RMA IN"
   - How to validate incoming pickings

3. **Replacement Process**
   - When to use "Issue Replacement"
   - How to handle under-warranty vs. out-of-warranty

4. **Quick Invoice**
   - Alternative to SO for OOW claims
   - When to use direct invoice

---

## 📚 Additional Resources

- **RMA_FEATURES_DOCUMENTATION.md** - Complete feature guide
- **RMA_IMPLEMENTATION_SUMMARY.md** - Technical implementation details
- **QUICKSTART.md** - Basic module usage (if exists)
- **README.md** - Module overview

---

## 📞 Support

If you encounter issues during upgrade:

1. Check Odoo logs:
   ```bash
   tail -f /var/log/odoo/odoo-server.log
   ```

2. Enable debug mode and check Technical menu

3. Review this guide's troubleshooting section

4. Check module documentation files

---

## ✅ Upgrade Complete Checklist

After successful upgrade, verify:

- ✅ Module shows as installed in Apps
- ✅ Settings section visible and configurable
- ✅ Existing claims still accessible
- ✅ New claim lines tab visible
- ✅ RMA wizards open correctly
- ✅ No JavaScript errors in console
- ✅ Users can access based on their group
- ✅ Configuration saved successfully

---

**Upgrade Version:** 17.0.1.0.0 → 17.0.2.0.0  
**Estimated Upgrade Time:** 2-5 minutes  
**Downtime Required:** Optional (5 minutes if stopping Odoo)  
**Risk Level:** Low (no data loss expected)

---

**Good luck with your upgrade!** 🚀
