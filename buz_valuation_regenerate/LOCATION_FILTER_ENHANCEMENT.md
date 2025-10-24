# Location Filter Enhancement - Valuation Regenerate Module

## Overview
Enhanced the `buz_valuation_regenerate` module to support filtering by stock locations when regenerating valuation layers and journal entries.

## Version
- Updated from: `17.0.1.0.0`
- Updated to: `17.0.1.1.0`

## Changes Made

### 1. Wizard Model (`models/valuation_regenerate_wizard.py`)

#### Added Fields
- `location_ids`: Many2many field to select specific stock locations
  - Domain: `[('usage', 'in', ['internal', 'transit'])]`
  - Optional: Leave empty to process all locations
  - Help text: "Filter by specific stock locations. Leave empty to process all locations."

#### Added Methods
- `_onchange_company_id()`: Clears location selection when company changes and updates location domain

#### Modified Methods
- `_find_svl_to_delete()`: Now filters SVLs by location when `location_ids` is set
  - Checks if stock move's `location_id` or `location_dest_id` matches selected locations
  
- `_recompute_fifo_valuation()`: Filters stock moves by location
  - Applies location filter to both provided stock moves and searched moves
  - Uses OR logic: includes moves where either source or destination location matches
  
- `_recompute_avco_valuation()`: Filters stock moves by location
  - Same filtering logic as FIFO method
  
- `_create_backup_log()`: Saves selected locations to the log

### 2. Log Model (`models/valuation_regenerate_log.py`)

#### Added Fields
- `scope_location_ids`: Many2many field to record which locations were filtered
  - Read-only field for historical tracking

### 3. Wizard View (`views/wizard_views.xml`)

#### UI Changes
- Added location selector field after company and date range fields
- Widget: `many2many_tags` for easy multi-selection
- Placeholder text: "All locations (leave empty for all)"

### 4. Log View (`views/log_views.xml`)

#### UI Changes
- Added `scope_location_ids` field to tree view
- Added `scope_location_ids` field to form view in the Scope section
- Both use `many2many_tags` widget for consistent display

### 5. Manifest (`__manifest__.py`)

#### Updated
- Summary: Added "/location" to indicate new filtering capability
- Description: 
  - Updated to mention location filtering
  - Added detailed features list
  - Noted "new in v1.1.0" for location filter
- Version: Bumped to `17.0.1.1.0`

## How It Works

### Location Filtering Logic

1. **User Selection**: Users can optionally select one or more locations in the wizard

2. **SVL Filtering**: When finding SVLs to delete:
   ```python
   svls.filtered(lambda svl: 
       svl.stock_move_id.location_id.id in location_ids or
       svl.stock_move_id.location_dest_id.id in location_ids
   )
   ```

3. **Stock Move Filtering**: When regenerating valuations:
   - For provided moves (from deleted SVLs):
     ```python
     stock_moves.filtered(lambda m:
         m.location_id.id in location_ids or
         m.location_dest_id.id in location_ids
     )
     ```
   - For searched moves (fallback):
     ```python
     domain.append(
         '|',
         ('location_id', 'in', location_ids),
         ('location_dest_id', 'in', location_ids)
     )
     ```

4. **Log Storage**: Selected locations are stored in the log for audit trail

## Usage Example

### Scenario: Regenerate valuation for WH/Stock location only

1. Open the wizard: Inventory → Operations → Re-Generate Valuation Layers
2. Select Company: "Your Company"
3. Select Mode: "Products" and choose products
4. Select Locations: "WH/Stock"
5. Set Date Range (optional)
6. Click "Compute Plan" to preview
7. Disable "Dry Run Mode"
8. Click "Apply Regeneration"

Only stock valuation layers associated with stock moves involving WH/Stock location will be regenerated.

## Benefits

1. **Precision**: Target specific warehouses or locations for valuation regeneration
2. **Performance**: Process fewer records by filtering early
3. **Flexibility**: Can still process all locations by leaving field empty
4. **Audit Trail**: Logs record which locations were filtered
5. **Safety**: Works with existing dry-run and backup features

## Compatibility

- Compatible with existing module functionality
- Backward compatible: Empty location_ids processes all locations (default behavior)
- Works with both FIFO and AVCO costing methods
- Works with Landed Costs scenarios

## Testing Recommendations

1. Test with single location selected
2. Test with multiple locations selected
3. Test with no locations selected (should process all)
4. Test with FIFO costing method
5. Test with AVCO costing method
6. Verify log records location filters correctly
7. Test with date range + location combination
8. Verify dry-run mode shows correct preview with location filter

## Notes

- Location filter uses OR logic: includes moves where **either** source **or** destination matches
- Only "internal" and "transit" location types are available for selection
- Location domain is automatically filtered by selected company
- When company changes, location selection is cleared to avoid cross-company issues
