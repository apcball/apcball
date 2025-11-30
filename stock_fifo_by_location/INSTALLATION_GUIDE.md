# Installation Guide for Existing Databases

## Overview

When installing `stock_fifo_by_location` module on an **existing database** with historical stock data, the module will automatically fix valuation issues through a **post-install hook**.

## What Happens During Installation?

The post-install hook automatically performs:

1. ✅ **Fix NULL remaining values** - Sets `remaining_value = 0.0` for negative layers
2. ✅ **Recalculate remaining qty/value** - Recalculates all remaining quantities per warehouse using FIFO
3. ✅ **Fix value mismatch** - Fixes products where `qty=0` but `value≠0`
4. ✅ **Verification** - Checks database consistency after fixes

## Installation Steps

### For Fresh/New Database
```bash
# Standard installation - no additional steps needed
odoo-bin -d your_database -i stock_fifo_by_location
```

The post-install hook will run automatically but will find no data to fix (which is fine).

### For Existing Database with Historical Data

#### Step 1: Backup Database ⚠️
```bash
# CRITICAL: Always backup before installation
pg_dump your_database > backup_$(date +%Y%m%d_%H%M%S).sql
```

#### Step 2: Install Module
```bash
# Via command line
odoo-bin -d your_database -i stock_fifo_by_location

# Or via UI
Apps > Search "Stock FIFO by Warehouse" > Install
```

#### Step 3: Monitor Installation
The post-install hook will log progress:
```
INFO: Running post-install hook for stock_fifo_by_location
INFO: Step 1: Fixing NULL remaining values...
INFO: ✅ Fixed 3927 layers with NULL remaining_value
INFO: Step 2: Recalculating remaining qty/value per warehouse...
INFO:   Processing warehouse: คลังวัตถุดิบ 1 (RM01)
INFO:     Progress: 100 products processed...
INFO: ✅ Processed 3329 products, updated 20488 layers
INFO: Step 3: Fixing value mismatch...
INFO: ✅ Fixed 144 products with value mismatch
INFO: Step 4: Verification...
INFO: Total products: 2543
INFO: Value mismatch: 0
INFO: Remaining mismatch: 0
INFO: ✅ Post-install hook completed successfully!
```

#### Step 4: Verify Installation

**Via SQL:**
```sql
-- Check for remaining issues
SELECT 
    COUNT(*) as total_products,
    COUNT(CASE WHEN ABS(total_qty) < 0.01 AND ABS(total_value) > 0.01 THEN 1 END) as value_mismatch
FROM (
    SELECT 
        pp.id,
        SUM(svl.quantity) as total_qty,
        SUM(svl.value) as total_value
    FROM stock_valuation_layer svl
    JOIN product_product pp ON pp.id = svl.product_id
    GROUP BY pp.id
) sub;
```
Expected result: `value_mismatch = 0`

**Via UI:**
```
Inventory > Configuration > Recalculate Valuation
```
- Open the wizard
- Check verification results at the bottom

## If Post-Install Hook Fails

If the post-install hook encounters an error:

1. **Check Logs:**
   ```bash
   tail -f /var/log/odoo/your_instance.log | grep "post-install"
   ```

2. **Run Manual Fix:**
   ```
   Inventory > Configuration > Recalculate Valuation
   ```
   - Select all warehouses (or leave empty)
   - Enable all three options
   - Click "Start Recalculation"

3. **Or use Python script:**
   ```bash
   python3 /path/to/recalculate_remaining_by_warehouse.py
   ```

## Installation Time Estimates

| Database Size | Products | Layers | Estimated Time |
|--------------|----------|--------|----------------|
| Small        | < 500    | < 5K   | 1-2 minutes    |
| Medium       | 500-2K   | 5K-20K | 2-5 minutes    |
| Large        | 2K-5K    | 20K-50K| 5-15 minutes   |
| Very Large   | > 5K     | > 50K  | 15+ minutes    |

## Common Issues and Solutions

### Issue 1: Installation Timeout
**Symptom:** Installation process times out before completing

**Solution:**
1. Increase timeout in `odoo.conf`:
   ```ini
   [options]
   limit_time_cpu = 3600
   limit_time_real = 7200
   ```
2. Restart Odoo and retry installation

### Issue 2: Memory Error
**Symptom:** Out of memory error during installation

**Solution:**
1. Install module via command line instead of UI
2. Increase server memory if possible
3. Run manual fix wizard after installation with warehouses in batches

### Issue 3: Some Products Still Have Issues
**Symptom:** Verification shows `value_mismatch > 0` after installation

**Solution:**
Run the wizard manually:
```
Inventory > Configuration > Recalculate Valuation
```

## Uninstallation

To uninstall (if needed):
```bash
odoo-bin -d your_database -u stock_fifo_by_location --uninstall
```

**Warning:** Uninstalling will:
- Remove `warehouse_id` field from valuation layers
- Remove custom FIFO calculations
- Revert to standard Odoo FIFO (no per-warehouse tracking)

## Support

If you encounter issues:
1. Check logs: `/var/log/odoo/your_instance.log`
2. Run wizard manually: `Inventory > Configuration > Recalculate Valuation`
3. Check scripts: `/path/to/module/scripts/`
4. Contact: GitHub Issues or support email

## Testing on Staging

**Recommended workflow:**
1. ✅ Backup production database
2. ✅ Restore to staging environment
3. ✅ Install module on staging
4. ✅ Verify results
5. ✅ Test valuation reports
6. ✅ If all OK, proceed with production

---

**Version:** v17.0.1.1.4  
**Last Updated:** 2025-11-28
