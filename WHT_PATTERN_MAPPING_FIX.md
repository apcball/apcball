# WHT Clear Advance - Pattern Mapping Fix

## Problem Analysis
Based on your diagnostic output:

```
📋 **Withholding Tax Configuration Analysis** 
Found 1 withholding tax records 
Available fields: name, amount 
• Name: WHT 3% C S | Amount: 3.0% | ⚠️ No direct link to account.tax found 

🎯 **Taxes matching WHT criteria:** 15 
• 1% WH C T (-1.0%) - purchase 
• 2% WH C A (-2.0%) - purchase 
• 3% WH C S (-3.0%) - purchase 
• 5% WH C R (-5.0%) - purchase 
• 1% WH P T (-1.0%) - purchase 
• 2% WH P A (-2.0%) - purchase 
• 3% WH P S (-3.0%) - purchase 
• 5% WH P R (-5.0%) - purchase 
```

## Issue Identified
1. **Configuration**: `account.withholding.tax` has "WHT 3% C S" (3.0%)
2. **Actual Taxes**: `account.tax` has "3% WH C S" (-3.0%)
3. **Problem**: Name pattern doesn't match ("WHT 3%" vs "3% WH")
4. **Missing**: No direct field linking the two models

## Solution Implemented

### 1. Enhanced Pattern Mapping (`_map_withholding_tax_to_account_tax`)
```python
# Converts "WHT 3% C S" → "3% WH C S"
wht_match = re.match(r'WHT\s+(\d+)%\s+(.+)', wht_name)
if wht_match:
    percentage = wht_match.group(1)  # "3"
    suffix = wht_match.group(2)      # "C S"
    tax_pattern = f"{percentage}% WH {suffix}"  # "3% WH C S"
```

### 2. Enhanced Domain Filter
- **Pattern Recognition**: Specifically looks for "X% WH Y Z" patterns
- **Multiple Criteria**: Checks company, negative amount, active status
- **Your System Pattern**: `^\d+%\s+WH\s+[A-Z]+(\s+[A-Z]+)*$`

### 3. Enhanced Validation
```python
# Validates your system's pattern: "3% WH C S"
wht_pattern = re.compile(r'^\d+%\s+WH\s+[A-Z]+(\s+[A-Z]+)*$')
if wht_pattern.match(tax_name_upper):
    return True
```

### 4. Multiple Mapping Attempts
1. **Pattern Conversion**: "WHT 3% C S" → "3% WH C S"
2. **Name Variations**: Try WHT/WH replacements  
3. **Amount Matching**: Match by tax rate (-3.0%)

## Expected Results

After the fix, the wizard should now:

✅ **Properly Map**: "WHT 3% C S" → "3% WH C S"
✅ **Show Only Valid WHT**: Only the 15 matching taxes in dropdown
✅ **Auto-Detection**: Automatically detect "3% WH C S" when it matches bill
✅ **Validation**: Confirm the tax is legitimate WHT

## Test Instructions

1. **Open Clear Advance Wizard** from any expense sheet/bill
2. **Click "Show Available WHT Taxes"** - should show:
   ```
   ✅ Maps to: 3% WH C S (-3.0%)
   📊 Mapping Result: 1/1 successfully mapped
   ```
3. **WHT Tax Dropdown** should now show only the 15 valid WHT taxes
4. **Auto-detect WHT** should work if bill contains "3% WH C S"

## Technical Details

### Files Modified
- `employee_advance/wizards/wht_clear_advance_wizard.py`
  - Added `_map_withholding_tax_to_account_tax()` method
  - Enhanced `_get_wht_tax_domain()` with pattern matching
  - Improved `_validate_wht_tax()` with regex validation
  - Updated diagnostic tools with mapping analysis

### Pattern Rules Implemented
1. **"WHT X% Y Z"** → **"X% WH Y Z"** (primary conversion)
2. **Negative amounts required** for all WHT taxes
3. **Regex validation** for system-specific patterns
4. **Multi-criteria validation** with fallbacks

## Benefits
- ✅ Accurate WHT tax selection from your l10n_th_account_tax configuration
- ✅ Prevents VAT tax selection as WHT
- ✅ Automatic pattern recognition and mapping
- ✅ Enhanced debugging and analysis tools
- ✅ Thai compliance with proper tax codes (C=Company, P=Personal, etc.)

Date: October 4, 2025