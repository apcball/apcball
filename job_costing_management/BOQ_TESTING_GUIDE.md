# BOQ Duplication - Quick Testing Guide

## What Was Fixed

### 1. **XML Parsing Error**
- **Issue**: `view_type` field is deprecated in Odoo 17
- **Fix**: Removed `view_type` field from `action_boq_duplicate` in `views/boq_views.xml`

### 2. **BOQ Copy Method Enhancement**
- **Issue**: Products were not being copied properly
- **Fix**: Enhanced `copy()` method in `models/boq.py` to manually copy all fields including products

### 3. **Added Duplicate Button**
- **Location**: BOQ form view header
- **Function**: Calls `action_duplicate()` method which uses the enhanced copy functionality

## How to Test

### Method 1: Using the Duplicate Button (Recommended)
1. **Open any BOQ record** with products in the lines
2. **Click "Duplicate" button** in the header
3. **Verify** that the new BOQ opens with:
   - All products properly copied
   - Title shows "(Copy)" suffix
   - State is "Draft"
   - All line details preserved

### Method 2: Using the Test Wizard
1. **Go to Job Costing > Configuration > Test BOQ Duplication**
2. **Click "Test Duplication"**
3. **Review** the success message showing:
   - Original vs new BOQ details
   - Line count comparison
   - Product copy status

### Method 3: Manual Testing (Advanced)
1. **Create a BOQ** with multiple lines containing different products
2. **Use standard Odoo duplicate** (Action > Duplicate)
3. **Verify** that products are properly copied
4. **Compare** original vs duplicate to ensure data integrity

## Expected Results

### ✅ Success Indicators
- **Products preserved**: All product fields are populated in the copy
- **Relationships maintained**: Categories, UOM, etc. are correctly linked
- **State reset**: New BOQ is in "Draft" state
- **Title updated**: Shows "(Copy)" suffix
- **Lines copied**: All BOQ lines are duplicated with correct data

### ❌ Failure Indicators
- **Blank products**: Product fields are empty in copied lines
- **Missing relationships**: Categories or UOM are not linked
- **Wrong state**: New BOQ is not in "Draft" state
- **No lines**: BOQ copy has no lines

## Troubleshooting

### If Products Are Still Blank
1. **Check server logs** for any errors during copy process
2. **Verify** that the module was properly upgraded
3. **Test** with a simple BOQ with only one product line
4. **Check** if the `action_duplicate` method is available in the BOQ model

### If Duplicate Button Doesn't Work
1. **Restart Odoo service**: `sudo systemctl restart odoo17`
2. **Update module**: Go to Apps > Job Costing Management > Upgrade
3. **Check** for any XML parsing errors in the logs
4. **Verify** the button is visible in the form view

## Files Modified

### Core Implementation
- `models/boq.py` - Enhanced copy methods
- `views/boq_views.xml` - Added duplicate button, fixed XML issues

### Testing
- `models/test_boq_duplication.py` - Test wizard
- `views/test_boq_duplication_views.xml` - Test wizard view
- `__manifest__.py` - Updated data files list

## Final Status

**✅ IMPLEMENTED AND TESTED**

The BOQ duplication functionality now works correctly with proper product copying. The issue of blank products in BOQ duplicates has been resolved.

## Support

If you encounter any issues:
1. Check the server logs for detailed error messages
2. Use the test wizard to verify functionality
3. Ensure all files are properly saved and the module is upgraded
4. Contact technical support if problems persist
