# Mark as Done Feature - Automatic Transfer of Unallocated Materials

## Overview

This feature adds a "Mark as Done" button to material allocation wizards, allowing users to automatically transfer all unallocated materials to the destination location and mark the stock request as "Done" in a single action.

## Features

### 1. "Mark as Done" Button
- **Location**: Available in both single MO and multi-MO allocation wizards
- **Visibility**: Only appears when unallocated materials exist
- **Style**: Warning button (btn-warning) to indicate significant action
- **Confirmation**: Opens confirmation dialog before executing

### 2. Confirmation Wizard
- **Display**: Shows clear summary of what will happen
- **Information**: Lists all materials to be transferred
- **Warning**: Indicates action cannot be undone
- **Details**: Shows source and destination locations

### 3. Automatic Transfer
- **Creates**: New stock picking for unallocated materials
- **Transfers**: All materials from source to destination location
- **Validates**: Picking automatically
- **Updates**: Stock request state to "Done"

## User Flow

### Standard Allocation Flow
```
Allocation Wizard
    ↓ (only shows if unallocated materials exist)
"Mark as Done" button
    ↓
Confirmation Dialog
    ↓
- Shows list of materials to transfer
- Shows source → destination locations
- Warns about automatic action
    ↓
User confirms
    ↓
- Creates stock transfer
- Validates transfer
- Changes request status to "Done"
- Logs action in chatter
    ↓
Wizard closes
```

### Before vs After

#### Before (Manual Process)
1. Identify unallocated materials
2. Create manual stock transfer
3. Validate transfer
4. Navigate back to stock request
5. Change status to "Done"
6. Log action manually

#### After (One-Click Process)
1. Click "Mark as Done" in allocation wizard
2. Review confirmation dialog
3. Click "Confirm"
4. Everything happens automatically

## Technical Implementation

### New Models

#### `mrp.stock.request.mark.done.wizard`
Main confirmation wizard model.

**Fields:**
- `request_id`: Stock Request (readonly, pre-filled)
- `line_ids`: One2many to wizard lines
- `summary_html`: HTML summary of actions
- `has_unallocated`: Boolean - indicates if materials exist

**Methods:**
- `default_get()`: Populates wizard with unallocated materials
- `action_confirm()`: Creates transfer and marks as done
- `_validate_lines()`: Validates before processing
- `_create_transfer_picking()`: Creates stock transfer
- `_log_action()`: Logs in chatter

#### `mrp.stock.request.mark.done.wizard.line`
Wizard line model for individual materials.

**Fields:**
- `wizard_id`: Parent wizard
- `request_line_id`: Source request line
- `product_id`: Product (readonly)
- `uom_id`: Unit of measure (readonly)
- `qty_to_transfer`: Quantity to transfer (readonly)
- `available_qty`: Available quantity (readonly)

### Enhanced Existing Models

#### Single MO Wizard (`mrp.production.allocate.wizard`)
**New Field:**
- `has_unallocated_materials`: Boolean - computed field

**New Method:**
- `action_mark_as_done()`: Opens confirmation wizard

#### Multi-MO Wizard (`mrp.stock.request.allocate.multi.wizard`)
**New Field:**
- `has_unallocated_materials`: Boolean - computed field

**New Method:**
- `action_mark_as_done()`: Opens confirmation wizard

## Validation & Safety

The feature includes comprehensive validation:

1. **Material Availability Check**:
   - Only shows button when unallocated materials exist
   - Validates quantities before transfer

2. **State Validation**:
   - Only works with stock requests in 'requested' or 'done' state
   - Prevents action on cancelled/draft requests

3. **Quantity Validation**:
   - Ensures transfer quantities don't exceed available
   - Respects UoM precision

4. **User Confirmation**:
   - Requires explicit user confirmation
   - Shows clear warning about irreversible action

## Logging & Traceability

### Stock Request Chatter
```
Stock request marked as Done.

Automatic Transfer Created: WH/IN/00001
Materials Transferred:
• 10.00 Unit(s) of Product A
• 5.00 Unit(s) of Product B
```

### Transfer Picking
- **Origin**: "Auto-transfer: [Request Name]"
- **Note**: "Automatic transfer of unallocated materials when marking request as Done"
- **Link**: Linked to original stock request

## Benefits

### For Production Teams
✅ **One-click completion**: No manual transfer creation needed  
✅ **Clear visibility**: See exactly what will be transferred  
✅ **Error prevention**: Validations prevent mistakes  
✅ **Time saving**: Eliminates multi-step process  

### For Warehouse Teams
✅ **Clear transfers**: Automatic picking with proper documentation  
✅ **Full traceability**: Linked to original request  
✅ **Accurate quantities**: Based on real-time data  

### For Managers
✅ **Audit trail**: Complete chatter logs  
✅ **Process consistency**: Same flow for all users  
✅ **Data integrity**: Validations ensure accuracy  

## Configuration

No configuration required. The feature automatically:
- Detects unallocated materials
- Shows/hides button based on availability
- Uses existing stock request locations
- Leverages existing picking types

## Troubleshooting

### Button not visible
**Cause**: No unallocated materials available
**Solution**: 
1. Check if stock request has unallocated materials
2. Verify materials have been issued (picking validated)
3. Confirm some materials haven't been allocated already

### "No unallocated materials" error
**Cause**: All materials already allocated
**Solution**: 
1. Review allocation history
2. Check if request should already be "Done"
3. Verify no materials were missed

### Transfer creation fails
**Cause**: Location or picking type issues
**Solution**: 
1. Verify source and destination locations
2. Check picking type configuration
3. Ensure user has proper permissions

## API / Development

### Call from code
```python
# Get wizard
wizard = self.env['mrp.stock.request.mark.done.wizard'].create({
    'request_id': request.id,
})

# Open wizard
return {
    "name": _("Mark Stock Request as Done"),
    "type": "ir.actions.act_window",
    "view_mode": "form",
    "res_model": "mrp.stock.request.mark.done.wizard",
    "target": "new",
    "res_id": wizard.id,
}
```

### Extend wizard
```python
class MrpStockRequestMarkDoneWizard(models.TransientModel):
    _inherit = "mrp.stock.request.mark.done.wizard"
    
    # Add custom fields or methods
    custom_field = fields.Char()
```

## Related Features

- **Material Allocation**: Standard allocation process
- **Quick Allocation**: Direct allocation from MO
- **Multi-MO Allocation**: Allocate to multiple MOs
- **Stock Request Creation**: Create requests from MO

## Future Enhancements

Potential improvements for future versions:
1. **Bulk operations**: Mark multiple requests as done
2. **Partial transfers**: Transfer only selected materials
3. **Scheduled transfers**: Schedule transfers for future dates
4. **Mobile support**: Mobile-optimized confirmation dialog
5. **Barcode integration**: Scan materials for transfer

## Status

✅ **Feature Complete**  
✅ **Tested and Working**  
✅ **Documented**  
✅ **Ready for Production Use**

---

*Feature implemented: 2025-01-28*  
*Module: buz_mrp_stock_request v17.0.1.0.0*  
*Odoo Version: 17.0 Community Edition*