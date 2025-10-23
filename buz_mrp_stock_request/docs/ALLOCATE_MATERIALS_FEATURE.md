# Quick Allocate Materials Feature

## Overview

This feature adds a streamlined "Allocate Materials" button directly on Manufacturing Orders (MO), allowing users to quickly allocate available materials from stock requests without navigating away from the MO form.

## Features

### 1. Direct Allocation Button on MO
- **Location**: Manufacturing Order form view header (next to "Stock Request" button)
- **Visibility**: Only appears when materials are available to allocate
- **Badge**: Shows count of available material lines

### 2. Intelligent Detection
The system automatically detects when materials are available by:
- Checking all stock requests linked to the MO
- Identifying stock requests in 'requested' or 'done' state
- Finding lines with `qty_available_to_allocate > 0`

### 3. Simplified Wizard
When you click "Allocate Materials", a wizard opens with:
- **Pre-filtered materials**: Only shows materials available for this specific MO
- **Auto-populated quantities**: Defaults to maximum available quantity
- **Consolidated view**: Aggregates materials from all related stock requests
- **Lot/Serial support**: Automatic field display for tracked products
- **Editable quantities**: Adjust as needed or set to 0 to skip

## User Flow

### Before (Old Way - 6+ Steps)
1. Open MO
2. Click "Stock Requests" smart button
3. Select a stock request
4. Click "Allocate to MO"
5. Select the MO again from dropdown
6. Fill quantities and lots
7. Confirm

### After (New Way - 3 Steps)
1. Open MO
2. Click "Allocate Materials" button (visible only when materials available)
3. Review/adjust quantities and lots → Click "Allocate"

## Technical Details

### New Models

#### `mrp.production.allocate.wizard`
Main wizard model for quick allocation.

**Fields:**
- `mo_id`: Manufacturing Order (readonly, pre-filled)
- `line_ids`: One2many to wizard lines
- `company_id`: Related from MO
- `note`: HTML help text

**Methods:**
- `default_get()`: Prefills wizard lines with available materials
- `action_allocate()`: Performs allocation and consumption
- `_validate_allocations()`: Validates before processing

#### `mrp.production.allocate.wizard.line`
Individual material lines in the wizard.

**Fields:**
- `wizard_id`: Parent wizard
- `request_id`: Source stock request (readonly)
- `request_line_id`: Source request line (readonly)
- `product_id`: Product (readonly)
- `uom_id`: Unit of measure (readonly)
- `available_qty`: Available quantity (readonly)
- `qty_to_consume`: Editable quantity to consume
- `lot_id`: Lot/Serial number (required for tracked products)
- `tracking`: Product tracking type
- `notes`: Optional notes

**Methods:**
- `_perform_consumption()`: Creates stock move lines for consumption

### Extended Models

#### `mrp.production`
**New Fields:**
- `has_available_to_allocate`: Boolean - indicates materials available
- `available_allocations_count`: Integer - count of available material lines

**New Methods:**
- `_compute_has_available_to_allocate()`: Computes availability fields
- `action_allocate_materials_quick()`: Opens the quick allocation wizard

## Installation

The feature is automatically available after updating the module. No additional configuration required.

## Usage Examples

### Example 1: Basic Allocation
1. You have MO `WH/MO/00025` that needs materials
2. Materials were issued via Stock Request `SRQ/2025/00010`
3. Open MO `WH/MO/00025`
4. See "Allocate Materials" button with badge showing available items
5. Click button → Wizard shows all available materials
6. Review quantities (pre-filled with maximum available)
7. Click "Allocate" → Materials consumed to MO

### Example 2: Partial Allocation
1. Open MO with 5 materials available
2. Click "Allocate Materials"
3. Adjust quantities:
   - Product A: Keep full quantity (10 units)
   - Product B: Reduce to 5 units (10 available)
   - Product C: Set to 0 (skip allocation)
   - Product D: Keep full quantity with Lot number
   - Product E: Set to 0 (will allocate later)
4. Click "Allocate" → Only selected quantities consumed

### Example 3: Lot/Serial Tracked Products
1. Open MO
2. Click "Allocate Materials"
3. For products with lot tracking:
   - Lot/Serial field automatically visible
   - Select lot from dropdown or create new
   - For serial numbers: Quantity must be 1.0
4. Click "Allocate" → Materials consumed with lot traceability

## Benefits

### For Production Users
- **Faster operations**: 3 clicks instead of 6+
- **No navigation**: Stay on the MO form
- **Clear visibility**: See exactly what's available
- **Smart defaults**: Pre-filled quantities save time

### For Production Managers
- **Streamlined workflow**: Reduced training time
- **Better UX**: Intuitive and context-aware
- **Full traceability**: All allocations logged in chatter

### For System
- **Consistent data**: Same validation as original wizard
- **Full audit trail**: Messages posted to both MO and Stock Request
- **Automatic updates**: Quantities recalculated after allocation

## Validation & Safety

The wizard performs comprehensive validation:

1. **Quantity checks**:
   - Must be positive
   - Cannot exceed available quantity
   - Respects UoM precision

2. **Tracking requirements**:
   - Lot/Serial required for tracked products
   - Serial products: quantity must be 1.0

3. **State checks**:
   - MO must be in valid state (not done/cancelled)
   - Stock requests must be in 'requested' or 'done' state

4. **Allocation limits**:
   - Total allocated cannot exceed issued quantity
   - System prevents over-allocation

## Logging & Traceability

### MO Chatter Log
```
Materials allocated and consumed:
• 10.0 Unit(s) of Product A (from SRQ/2025/00010) - Lot: LOT001
• 5.0 Unit(s) of Product B (from SRQ/2025/00010)
```

### Stock Request Chatter Log
```
Materials allocated to WH/MO/00025:
• 10.0 Unit(s) of Product A - Lot: LOT001
• 5.0 Unit(s) of Product B
```

## Configuration

No configuration required. The feature automatically:
- Detects available materials
- Shows/hides button based on availability
- Pre-filters materials for the current MO

## Troubleshooting

### Button not visible
**Cause**: No materials available to allocate
**Solution**: 
1. Check if MO has linked stock requests
2. Verify stock requests are in 'requested' or 'done' state
3. Confirm materials have been issued (picking validated)
4. Check that materials haven't already been fully allocated

### "No materials available" error
**Cause**: Button was clicked but no materials found
**Solution**: Refresh the page or check stock request status

### Lot/Serial field not showing
**Cause**: Product tracking is set to 'none'
**Solution**: Check product configuration for tracking settings

### Cannot allocate more than available
**Cause**: Trying to consume more than issued quantity
**Solution**: Either:
1. Reduce quantity in wizard
2. Issue more materials via stock request
3. Split allocation across multiple operations

## API / Development

### Call from code
```python
# Get MO
mo = self.env['mrp.production'].browse(mo_id)

# Check if materials available
if mo.has_available_to_allocate:
    # Open wizard
    action = mo.action_allocate_materials_quick()
    return action
```

### Extend wizard
```python
class MrpProductionAllocateWizard(models.TransientModel):
    _inherit = "mrp.production.allocate.wizard"
    
    # Add custom fields or methods
    custom_field = fields.Char()
```

## Related Features

- **Stock Request Creation**: Create stock requests from MO
- **Original Allocation Wizard**: Allocate from stock request view (multi-MO)
- **Smart Buttons**: Navigate between MO ↔ Stock Requests ↔ Pickings

## Future Enhancements

Potential improvements for future versions:
1. Bulk allocation for multiple MOs
2. Automatic lot selection based on FIFO/FEFO
3. Allocation templates/presets
4. Mobile-optimized view
5. Barcode scanning integration
