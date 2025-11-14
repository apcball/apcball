# Installation & Deployment Checklist

## Pre-Installation

- [ ] Backup Odoo database
- [ ] Backup Odoo configuration files
- [ ] Verify Odoo 17 is running
- [ ] Verify stock module is installed
- [ ] Verify stock_account module is installed
- [ ] Ensure write permissions to custom-addons folder

## Installation Steps

### 1. Copy Module Files

```bash
# Navigate to custom-addons
cd /opt/instance1/odoo17/custom-addons

# Verify stock_fifo_by_location directory exists
ls -la stock_fifo_by_location/

# Check permissions
chmod -R 755 stock_fifo_by_location/
```

- [ ] Module directory copied
- [ ] File permissions set correctly
- [ ] All files present (see below)

### 2. Restart Odoo Service

```bash
# Option 1: SystemD
sudo systemctl restart instance1

# Option 2: Docker
docker restart odoo17

# Option 3: Manual
pkill -f odoo.py
# Wait 5 seconds, then start Odoo normally
```

- [ ] Service restarted
- [ ] Service is running (check logs)

### 3. Install Module via UI

1. Log in to Odoo with admin user
2. Activate **Developer Mode:**
   - Top right corner → Settings → Activate Debug Mode
3. Navigate to: **Apps**
4. Click **Update Apps List** (if needed)
5. Search for: `stock_fifo_by_location`
6. Click on module
7. Click **Install**

- [ ] Module appears in Apps list
- [ ] Module installs without errors
- [ ] Module status shows "Installed"

### 4. Verify Installation

Check that database changes were applied:

```bash
# Via database
psql -U odoo -d your_database -c \
  "SELECT column_name FROM information_schema.columns 
   WHERE table_name='stock_valuation_layer' AND column_name='location_id';"

# Should output: location_id
```

Also in Odoo UI:
1. Navigate to: **Inventory** → **Valuation Layers**
2. Verify `location_id` column is visible in list view
3. Open any existing layer
4. Verify `location_id` field shows in form view

- [ ] Database column exists
- [ ] UI shows location_id field
- [ ] No installation errors in logs

### 5. Configure Settings (Optional)

Navigate to: **Settings** → **Technical** → **Parameters**

Search and adjust as needed:

| Parameter | Current Value | Options |
|-----------|---------------|---------|
| `stock_fifo_by_location.shortage_policy` | error | error, fallback |
| `stock_fifo_by_location.enable_validation` | True | True, False |
| `stock_fifo_by_location.debug_mode` | False | True, False |

- [ ] Settings reviewed
- [ ] Shortage policy configured
- [ ] Debug mode set if needed

### 6. Run Migration (For Existing Data)

If you have existing stock movements, populate `location_id`:

**Option A: Via Python Shell (Recommended)**

```bash
cd /path/to/odoo17
python -m odoo.bin shell -d your_database

# In the shell:
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
result = populate_location_id.populate_location_id(env)
exit()
```

**Option B: Via Server Action (if available in UI)**

1. Navigate to: **Inventory** → **Valuation Layers**
2. Look for action: **Populate Location IDs**
3. Click and execute

**Option C: Manual Database Update (For Large Datasets)**

```sql
-- Populate from stock_move
UPDATE stock_valuation_layer svl
SET location_id = sm.location_dest_id
FROM stock_move sm
WHERE svl.stock_move_id = sm.id
  AND svl.location_id IS NULL;

-- Verify
SELECT COUNT(*) as unassigned 
FROM stock_valuation_layer 
WHERE location_id IS NULL;
```

- [ ] Migration script executed (if needed)
- [ ] Check for unassigned layers (should be 0 or minimal)
- [ ] Review logs for any migration issues

### 7. Run Tests (Optional but Recommended)

```bash
# Via Pytest
cd /path/to/odoo17
pytest -xvs addons/stock_fifo_by_location/tests/ -k "test_"

# Via Odoo
python -m odoo.bin -d your_database \
  -m stock_fifo_by_location \
  --test-enable
```

- [ ] Tests execute
- [ ] Tests pass (all green)
- [ ] No errors or warnings

### 8. Manual Testing

Perform manual tests to verify functionality:

See `MANUAL_TESTING.md` for detailed scenarios

- [ ] Scenario 1: Basic receiving ✅
- [ ] Scenario 2: Location isolation ✅
- [ ] Scenario 3: FIFO calculation ✅
- [ ] Scenario 4: Shortage handling ✅

## Post-Installation

### Monitor Logs

```bash
# Odoo logs
tail -f /var/log/odoo/instance1.log

# Database logs (if PostgreSQL)
tail -f /var/log/postgresql/postgresql.log
```

- [ ] No errors in logs
- [ ] No warnings about missing fields
- [ ] Performance appears normal

### Validate Data Integrity

```sql
-- Check for orphaned layers
SELECT COUNT(*) as orphaned 
FROM stock_valuation_layer 
WHERE location_id IS NULL;

-- Should return 0 or minimal

-- Check index exists
SELECT * FROM pg_stat_user_indexes 
WHERE schemaname='public' 
  AND tablename='stock_valuation_layer'
  AND indexname LIKE '%location_id%';
```

- [ ] No orphaned records
- [ ] Indexes exist and are being used
- [ ] Query performance is acceptable

## Rollback Plan (If Needed)

### Emergency Disable

```bash
# Via Odoo shell
python -m odoo.bin shell -d your_database

# In shell:
env['ir.module.module'].search([
    ('name', '=', 'stock_fifo_by_location')
]).button_uninstall()

exit()

# Or restart Odoo and uninstall via UI:
# Apps → Stock FIFO by Location → Uninstall
```

### Database Rollback

```sql
-- Remove column if rollback is complete
ALTER TABLE stock_valuation_layer DROP COLUMN IF EXISTS location_id;

-- Or restore from backup
restore_database_from_backup()
```

- [ ] Rollback procedure documented
- [ ] Backup verified and accessible

## Deployment Checklist Summary

```
PRE-INSTALLATION
  ✅ Database backed up
  ✅ Configuration backed up
  ✅ Dependencies verified

INSTALLATION
  ✅ Module copied
  ✅ Service restarted
  ✅ Module installed via UI
  ✅ Installation verified

CONFIGURATION
  ✅ Settings configured
  ✅ Migration run (if needed)
  ✅ Tests passed

VALIDATION
  ✅ Manual tests passed
  ✅ Data integrity verified
  ✅ Logs reviewed

READY FOR PRODUCTION
  ✅ All checks passed
  ✅ Documentation reviewed
  ✅ Team trained (if applicable)
```

## Support Contacts

For issues during deployment:

1. Check module README.md for common issues
2. Review logs: `/var/log/odoo/`
3. Check database: See troubleshooting queries in MANUAL_TESTING.md
4. Contact: Development team with error details

## Documentation

Module includes:

- `README.md` - Full module documentation
- `MANUAL_TESTING.md` - Step-by-step testing guide
- `INSTALLATION_CHECKLIST.md` - This file
- Code comments and docstrings throughout

## Module Files Summary

```
stock_fifo_by_location/
├── __manifest__.py                    ✅ Module metadata
├── __init__.py                        ✅ Package init
├── README.md                          ✅ Main documentation
├── MANUAL_TESTING.md                  ✅ Testing guide
├── INSTALLATION_CHECKLIST.md          ✅ This file
├── models/
│   ├── __init__.py                   ✅ Models init
│   ├── stock_valuation_layer.py      ✅ SVL extension
│   ├── stock_move.py                 ✅ Move override
│   └── fifo_service.py               ✅ FIFO service
├── security/
│   └── ir.model.access.csv           ✅ Access control
├── data/
│   └── config_parameters.xml         ✅ Default config
├── views/
│   └── stock_valuation_layer_views.xml ✅ UI views
├── migrations/
│   ├── __init__.py                   ✅ Migration init
│   └── populate_location_id.py       ✅ Migration script
└── tests/
    ├── __init__.py                   ✅ Tests init
    └── test_fifo_by_location.py      ✅ Unit tests

All files verified: ✅
```

## Next Steps

1. Review README.md for full feature documentation
2. Review MANUAL_TESTING.md for validation procedures
3. Train team on new location-based FIFO features
4. Monitor system for first few transactions
5. Schedule post-deployment review meeting

---

**Deployment Date:** ________________  
**Deployed By:** ________________  
**Verified By:** ________________  
**Notes:** _______________________________________________________________
