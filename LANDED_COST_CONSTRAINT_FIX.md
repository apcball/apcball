# Fix for Landed Cost Constraint Validation Error

## Problem

When attempting to delete landed cost records, the following error occurs:

```
Validation Error

The operation cannot be completed: another model requires the record being deleted. 
If possible, archive it instead.

Model: Landed Cost by Location (stock.valuation.layer.landed.cost)
Constraint: stock_valuation_layer_landed__valuation_adjustment_line_id_fkey
```

## Root Cause

The foreign key constraint `valuation_adjustment_line_id` in the `stock.valuation.layer.landed.cost` model was initially set with `ondelete='restrict'`. This prevented deletion of `stock.landed.cost.lines` records when they had associated location-based landed cost allocations.

## Solution

Changed the foreign key constraint from `RESTRICT` to `CASCADE`:

### Code Changes

**File:** `models/landed_cost_location.py`

```python
valuation_adjustment_line_id = fields.Many2one(
    'stock.landed.cost.lines',
    string='Valuation Adjustment Line',
    ondelete='cascade',  # Changed from 'restrict'
    help='Reference to the valuation adjustment line from landed cost.'
)
```

### Database Changes

The foreign key constraint has been updated:

**Before:**
```sql
FOREIGN KEY (valuation_adjustment_line_id) 
REFERENCES stock_landed_cost_lines(id) 
ON DELETE RESTRICT
```

**After:**
```sql
FOREIGN KEY (valuation_adjustment_line_id) 
REFERENCES stock_landed_cost_lines(id) 
ON DELETE CASCADE
```

## Implementation

### Files Modified

1. **`models/landed_cost_location.py`**
   - Changed `ondelete='restrict'` to `ondelete='cascade'`
   - Updated `unlink()` method for better error handling
   - Added `_sql_constraints = []` declaration

2. **`__manifest__.py`**
   - Updated version from `17.0.1.0.0` to `17.0.1.0.1`

3. **`migrations/17.0.1.0.1/post-migrate.py`** (NEW)
   - Migration script to update the database constraint
   - Automatically runs when module is upgraded

4. **`fix_landed_cost_constraint.sh`** (NEW)
   - Convenience script to apply the fix

## How to Apply the Fix

### Option 1: Using the Script (Recommended)

```bash
cd /opt/instance1/odoo17/custom-addons
./fix_landed_cost_constraint.sh
```

This script will:
1. Stop the Odoo service
2. Upgrade the module
3. Verify the constraint
4. Restart the service

### Option 2: Manual Upgrade via UI

1. Go to **Apps** menu
2. Remove the "Apps" filter
3. Search for "stock_fifo_by_location"
4. Click **Upgrade**

### Option 3: Command Line

```bash
sudo systemctl stop instance1

sudo -u mogenit /opt/instance1/odoo17/venv/bin/python3 \
    /opt/instance1/odoo17/odoo-bin \
    -c /opt/instance1/odoo17/config/odoo.conf \
    -d MOG_LIVE_15_08 \
    -u stock_fifo_by_location \
    --stop-after-init

sudo systemctl start instance1
```

## Verification

After applying the fix, verify the constraint:

```bash
sudo -u postgres psql MOG_LIVE_15_08 -c "
    SELECT 
        conname,
        CASE confdeltype 
            WHEN 'c' THEN 'CASCADE'
            WHEN 'n' THEN 'SET NULL'
            WHEN 'r' THEN 'RESTRICT'
        END as delete_action
    FROM pg_constraint
    WHERE conname = 'stock_valuation_layer_landed__valuation_adjustment_line_id_fkey';
"
```

Expected output:
```
                             conname                             | delete_action 
-----------------------------------------------------------------+---------------
 stock_valuation_layer_landed__valuation_adjustment_line_id_fkey | CASCADE
```

## Result

After applying this fix:

- ✓ Deleting `stock.landed.cost.lines` records will automatically delete associated `stock.valuation.layer.landed.cost` records
- ✓ No more validation errors when deleting landed cost records
- ✓ Data consistency is maintained through CASCADE behavior
- ✓ Proper cleanup of orphaned records

## Technical Details

### Cascade Behavior

When a `stock.landed.cost.lines` record is deleted:

1. Database automatically deletes all `stock.valuation.layer.landed.cost` records referencing it
2. No orphaned records remain in the database
3. No validation errors occur

### Alternative Approaches Considered

1. **SET NULL** - Would leave orphaned records with null references (not ideal)
2. **RESTRICT** - Prevents deletion (current problem)
3. **CASCADE** - Automatically cleans up related records (chosen solution)

### Migration Safety

The migration script:
- Checks if constraint exists before modifying
- Verifies current constraint type
- Only updates if needed
- Logs all operations
- Handles errors gracefully

## Testing

To test the fix:

1. Create a landed cost with location allocations
2. Try to delete the landed cost or its lines
3. Verify deletion succeeds without errors
4. Confirm related records are properly cleaned up

## Impact

- **Database:** Foreign key constraint updated
- **Performance:** No impact (CASCADE is efficient)
- **Data integrity:** Improved (no orphaned records)
- **User experience:** Deletion now works as expected

## Version History

- **17.0.1.0.0** - Initial version with RESTRICT constraint
- **17.0.1.0.1** - Fixed with CASCADE constraint (current)
