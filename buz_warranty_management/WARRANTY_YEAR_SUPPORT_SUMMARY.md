# Warranty Year Support Implementation Summary

## Overview
Added support for year-based warranty periods in addition to the existing month-based periods. Users can now configure warranties in either months or years.

## Version
Module version updated from `17.0.1.0.0` to `17.0.1.1.0`

## Changes Made

### 1. Product Template Model (`models/product_template.py`)
- **Modified Field**: `warranty_duration`
  - Changed label from "Warranty Duration (Months)" to "Warranty Duration"
  - Updated help text to be unit-agnostic
  
- **New Field**: `warranty_period_unit`
  - Type: Selection field
  - Options: 'month' (Month(s)) or 'year' (Year(s))
  - Default: 'month'
  - Purpose: Allows users to select the time unit for warranty duration

### 2. Warranty Card Model (`models/warranty_card.py`)
- **Modified Field**: `warranty_duration`
  - Changed label from "Duration (Months)" to "Duration"
  
- **New Field**: `warranty_period_unit`
  - Type: Selection field (related field)
  - Related to: `product_id.product_tmpl_id.warranty_period_unit`
  
- **Enhanced Method**: `_compute_end_date()`
  - Added dependency on `warranty_period_unit`
  - Implemented logic to calculate end date based on selected unit:
    - If unit is 'year': adds years using `relativedelta(years=duration)`
    - If unit is 'month': adds months using `relativedelta(months=duration)`
  - Maintains backward compatibility with default 12-month warranty

### 3. Product Template Views (`views/product_template_views.xml`)
- Redesigned warranty period input to show duration and unit side-by-side
- Added label "Warranty Period" for better clarity
- Duration field and unit selector displayed inline with appropriate widths

### 4. Warranty Card Views (`views/warranty_card_views.xml`)
- Updated warranty period display in form view
- Duration and unit shown inline for better user experience
- Maintains consistent styling with product template view

### 5. Warranty Certificate Report (`report/report_warranty_certificate.xml`)
- Updated duration display to dynamically show correct unit:
  - Shows "Year(s)" when warranty_period_unit is 'year'
  - Shows "Month(s)" for month-based warranties
- Ensures printed certificates reflect the correct warranty period

## Features

### User Benefits
1. **Flexible Configuration**: Choose between months or years for warranty duration
2. **Clearer Communication**: Warranty periods displayed with appropriate units
3. **Better User Experience**: Long-term warranties (e.g., "2 Years" instead of "24 Months")
4. **Backward Compatible**: Existing month-based warranties continue to work seamlessly

### Technical Benefits
1. **Accurate Calculations**: Proper date arithmetic using `relativedelta`
2. **Type Safety**: Selection field ensures valid unit values
3. **Related Fields**: Unit automatically propagates from product to warranty card
4. **Computed Fields**: End date automatically recalculates when unit or duration changes

## Usage Examples

### Example 1: 1 Year Warranty
- Set `warranty_duration` = 1
- Set `warranty_period_unit` = 'year'
- Result: Warranty card will expire exactly 1 year from start date

### Example 2: 6 Month Warranty
- Set `warranty_duration` = 6
- Set `warranty_period_unit` = 'month'
- Result: Warranty card will expire 6 months from start date

### Example 3: 2 Year Warranty
- Set `warranty_duration` = 2
- Set `warranty_period_unit` = 'year'
- Result: Warranty card will expire exactly 2 years from start date

## Migration Notes

### For Existing Data
- All existing warranty configurations will default to 'month' unit
- No data migration required as `warranty_period_unit` defaults to 'month'
- Existing warranty cards will continue to calculate correctly

### For New Installations
- Users can choose their preferred unit during product configuration
- System defaults to 'month' for consistency with previous behavior

## Testing Recommendations

1. **Create New Product with Year Warranty**
   - Enable "Auto Create Warranty"
   - Set duration to 2 and unit to "Year(s)"
   - Create and deliver a sales order
   - Verify warranty card shows correct end date (2 years from delivery)

2. **Test Month-Based Warranty**
   - Create product with 18 months warranty
   - Verify end date calculation is correct

3. **Print Warranty Certificate**
   - Generate warranty certificate for both year and month-based warranties
   - Verify correct unit displays in the printed report

4. **Test Existing Warranties**
   - Verify existing warranty cards still calculate correctly
   - Ensure no regression in existing functionality

## Files Modified

1. `__manifest__.py` - Version bump
2. `models/product_template.py` - Added warranty_period_unit field
3. `models/warranty_card.py` - Added unit field and enhanced calculation logic
4. `views/product_template_views.xml` - Updated warranty configuration layout
5. `views/warranty_card_views.xml` - Updated warranty period display
6. `report/report_warranty_certificate.xml` - Dynamic unit display in report

## Deployment Steps

1. Update the module in Odoo
2. Upgrade the module: Apps > Warranty Management > Upgrade
3. Clear browser cache if needed
4. Test with a sample product

## Support

For issues or questions, contact: apcball@buzzit.co.th
