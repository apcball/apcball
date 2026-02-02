# ⚠️ MODULE UPGRADE REQUIRED

## Current Status

The code changes have been applied to fix the FK constraint error:
- ✅ `AccountReceiptVoucher.unlink()` added (line 402)
- ✅ `AccountReceiptVoucherLine.unlink()` added (line 700)
- ✅ No syntax errors
- ✅ Odoo service restarted

## ⚠️ BUT: Module Not Yet Upgraded in Database

**The changes won't take effect until you upgrade the module in Odoo.**

Simply restarting the Odoo service is NOT enough. The Python code needs to be reloaded into the database registry.

---

## How to Upgrade the Module

Choose ONE of the following methods:

### Method 1: Upgrade via Odoo UI (Recommended)

1. **Enable Developer Mode:**
   - Go to Settings → Activate Developer Mode
   - Or add `?debug=1` to your URL

2. **Go to Apps:**
   - Click on "Apps" in the main menu

3. **Remove the "Apps" filter:**
   - Click the "🔍 Apps" filter button to remove it
   - This shows all modules including custom ones

4. **Find the module:**
   - Search for "buz_accounting_addon" or "BUZ Account Receipt"

5. **Upgrade:**
   - Click the "Upgrade" button
   - Wait for the upgrade to complete

6. **Test:**
   - Try to delete a receipt voucher
   - Should work without FK constraint error ✅

---

### Method 2: Command Line Upgrade

**Option A: Using the provided script**

```bash
cd /opt/instance1/odoo17/custom-addons
./upgrade_buz_accounting_addon.sh
# Enter your database name when prompted
```

**Option B: Direct command (replace YOUR_DATABASE with actual db name)**

```bash
# Stop instance
sudo systemctl stop instance1

# Upgrade module
sudo -u mogenit /opt/instance1/odoo17-venv/bin/python3 /opt/instance1/odoo17/odoo-bin \
    -c /etc/instance1.conf \
    -d YOUR_DATABASE \
    -u buz_accounting_addon \
    --stop-after-init

# Start instance
sudo systemctl start instance1
```

**Option C: Without stopping service (may cause lock)**

```bash
/opt/instance1/odoo17-venv/bin/python3 /opt/instance1/odoo17/odoo-bin \
    -c /etc/instance1.conf \
    -d YOUR_DATABASE \
    -u buz_accounting_addon \
    --stop-after-init \
    --logfile=/tmp/upgrade.log
```

---

### Method 3: Restart with Update Mode

```bash
# Edit the systemd service temporarily to add -u buz_accounting_addon
sudo systemctl edit --full instance1

# Add this to the ExecStart line:
# -u buz_accounting_addon

# Then restart:
sudo systemctl restart instance1

# After it starts, remove the -u flag and restart again
```

---

## How to Find Your Database Name

**Option 1: Check running connections**
```bash
sudo -u postgres psql -c "SELECT datname FROM pg_stat_activity WHERE usename = 'odoo17' AND datname != 'postgres' GROUP BY datname;"
```

**Option 2: List all Odoo databases**
```bash
sudo -u postgres psql -c "\l" | grep -E "odoo|UTF8"
```

**Option 3: Check Odoo logs**
```bash
sudo journalctl -u instance1 -n 100 | grep -i "database"
```

**Option 4: From Odoo UI**
- The database name is usually visible in the URL or in the database selector

---

## Verification After Upgrade

### 1. Check Module Version/State

Go to Odoo UI → Apps → Search "buz_accounting_addon" → Should show "Installed"

### 2. Test Deletion

```python
# In Odoo shell (python3 odoo-bin shell -c /etc/instance1.conf -d YOUR_DATABASE)
voucher = env['account.receipt.voucher'].search([], limit=1)
if voucher:
    print(f"Testing with voucher: {voucher.name}")
    # If it has unlink method, the code is loaded
    print(f"Has unlink method: {hasattr(voucher.__class__, 'unlink')}")
```

### 3. Check Logs

```bash
sudo journalctl -u instance1 -f
# Watch for any errors during upgrade
```

---

## Common Issues

### Issue 1: "Module not found"
**Solution:** Make sure the module is installed first:
- Go to Apps → Search "buz_accounting_addon" → Install
- Then upgrade

### Issue 2: "Database locked"
**Solution:** Stop the Odoo service first:
```bash
sudo systemctl stop instance1
# Run upgrade command
sudo systemctl start instance1
```

### Issue 3: "Permission denied"
**Solution:** Run commands with correct user:
```bash
sudo -u mogenit /opt/instance1/odoo17-venv/bin/python3 ...
```

### Issue 4: Still getting FK error after upgrade
**Solution:** Check if upgrade actually completed:
```bash
# Check logs for errors
sudo journalctl -u instance1 -n 200 | grep -i error

# Verify methods exist by searching in logs
sudo journalctl -u instance1 -n 1000 | grep -i "account_receipt_voucher"
```

---

## What Happens During Upgrade

1. Odoo reads the updated Python files
2. Reloads the models into the registry
3. Updates model definitions in `ir_model` and `ir_model_fields`
4. Runs any data files if version changed
5. The new `unlink()` methods become active

---

## After Successful Upgrade

You should be able to:
- ✅ Delete receipt vouchers (even with linked payments)
- ✅ Delete individual voucher lines
- ✅ No more FK constraint errors
- ✅ Payments remain in database (only M2M links are cleared)

---

## Need Help?

If you're unsure about your database name or need assistance:

1. Tell me your database name, and I'll give you the exact command
2. Or use Method 1 (UI upgrade) which doesn't require knowing the database name
3. Or run: `./upgrade_buz_accounting_addon.sh` and enter the database when prompted

---

**Next Step:** Choose one of the upgrade methods above and execute it.
