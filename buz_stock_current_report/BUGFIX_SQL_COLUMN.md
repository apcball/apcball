# 🐛 Bugfix Summary - SQL Column Errors

## Issues Fixed
**Error 1**: `psycopg2.errors.UndefinedColumn: column sl.display_name does not exist`  
**Error 2**: `psycopg2.errors.UndefinedColumn: column pp.display_name does not exist`

**Location**: `wizard/stock_current_export_wizard.py`, line 135 in `get_filtered_stock_data()` method

**Root Cause**: The SQL query used ORM property names (`display_name`) instead of actual database column names. Both `stock_location` and `product_template` tables use `name` column, not `display_name`.

## Affected Code
```python
# BEFORE (Line 135) - INCORRECT
query += " ORDER BY sl.display_name, pp.display_name"

# AFTER (Line 135) - CORRECT
query += " ORDER BY sl.name, pt.name"
```

## Traceback Analysis
```
psycopg2.errors.UndefinedColumn: column sl.display_name does not exist
LINE 43: AND sq.location_id IN (181) ORDER BY sl.display_nam...
                                            ^
File: buz_stock_current_report/wizard/stock_current_export_wizard.py
Method: get_filtered_stock_data()
Line: 136 (self.env.cr.execute)
```

## Solution Applied
Changed the SQL ORDER BY clause to use the correct database column names:
- `sl.display_name` → `sl.name` (stock_location table uses `name` column)
- `pp.display_name` → `pt.name` (use product_template `name` column instead)

The query already has access to the `product_template` table (aliased as `pt`), so we should order by `pt.name` instead of trying to access a non-existent `pp.display_name`.

## Important Finding
The query correctly selects from `product_template` (`pt`):
- `pt.categ_id` - product category
- `pt.uom_id` - unit of measure
- `pt.list_price` - unit cost

So the ORDER BY should use `pt.name` (product template name), not `pp.display_name`.

## Verification
The `stock_location` and `product_template` models use:
- **stock_location**: Column `name` (not `display_name`)
- **product_template**: Column `name` (not `display_name`)

When using raw SQL (`self.env.cr.execute`), we must use actual database column names, not ORM properties.

## Files Modified
- **File**: `wizard/stock_current_export_wizard.py`
- **Line**: 135
- **Change**: ORDER BY clause corrected to use actual database columns

## Testing Recommendation
After applying this fix, test the export feature:
1. Go to **Inventory** → **Reports** → **Export Current Stock to Excel**
2. Select date range and optional filters
3. Click **Export Excel**
4. Verify the export completes successfully without database errors

## Status
✅ **FIXED** - Both SQL column references corrected

---

**Date Fixed**: November 11, 2024  
**Version**: 17.0.1.0.2 (patch version)  
**Impact**: Critical (blocking export functionality)
**Resolution**: Two-step fix to correct ORDER BY clause column names
