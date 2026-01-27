# Multi-Product RMA IN Guide

## Overview

The Warranty Management module now supports multi-product RMA IN returns, allowing users to process multiple different parts/products in a single return operation. This enhancement improves efficiency and provides better tracking for complex warranty claims involving multiple components.

## Features

### Multi-Product Support
- **Multiple Part Selection**: Select and return multiple different products/parts in a single RMA IN operation
- **Individual Tracking**: Each returned part is tracked with its own line item, quantity, and serial/lot number
- **Return Reasons**: Add specific return reasons for each individual part
- **Flexible Quantities**: Support different quantities for each returned part

### Enhanced User Interface
- **Tabbed Layout**: Organized interface with separate tabs for return items and notes
- **Editable Grid**: Add, edit, and remove return lines directly in the wizard
- **Smart Defaults**: Automatically populates with the main claim product as the first line
- **Validation**: Ensures at least one return line is added before creating the RMA

## How to Use

### Creating a Multi-Product RMA IN

1. **Navigate to Warranty Claim**
   - Go to the warranty claim for which you want to create an RMA IN
   - Click the "Create RMA IN" button

2. **Configure Return Details**
   - Verify the claim and customer information (read-only)
   - Configure the picking type and destination location
   - Choose whether to generate a return label

3. **Add Return Items**
   - In the "Return Items" tab, you'll see the main claim product pre-populated
   - Click "Add a line" to add additional products/parts
   - For each line:
     - **Product**: Select the product to return
     - **Quantity**: Enter the quantity to return
     - **Lot/Serial Number**: Select the specific lot/serial if applicable
     - **Return Reason**: Add a specific reason for returning this part

4. **Add Notes (Optional)**
   - Switch to the "Notes" tab to add general notes about the return
   - These notes will appear on the picking

5. **Create RMA IN**
   - Click "Create RMA IN" to generate the return picking
   - The system will create a single picking with multiple stock moves
   - Each return line becomes a separate stock move

## Technical Details

### Data Model Changes

#### New Model: `warranty.rma.receive.line`
- **wizard_id**: Link to the main wizard
- **product_id**: Product being returned
- **lot_id**: Serial/lot number (optional)
- **qty**: Quantity to return
- **uom_id**: Unit of measure (auto-populated from product)
- **reason**: Return reason for this specific part

#### Modified Model: `warranty.rma.receive.wizard`
- **Removed**: Single product fields (`product_id`, `lot_id`, `qty`)
- **Added**: `line_ids` One2many field for multiple return lines
- **Enhanced**: `action_create_rma_picking()` method to handle multiple lines

### Integration Points

#### Stock Operations
- Creates one picking with multiple stock moves
- Each return line generates a separate stock move
- Maintains proper lot/serial tracking for each line

#### Claim Integration
- Links stock moves to matching claim lines when possible
- Updates claim status to 'awaiting_return'
- Posts activity messages with picking details

## Benefits

### For Users
- **Time Savings**: Process multiple returns in one operation
- **Better Organization**: All related returns grouped in a single picking
- **Detailed Tracking**: Individual tracking for each returned part
- **Flexible Workflow**: Handle both single and multi-product returns

### For Management
- **Improved Accuracy**: Reduced chance of missing returns
- **Better Reporting**: Clear visibility of all returned components
- **Streamlined Process**: Consistent workflow for all return types
- **Enhanced Audit Trail**: Detailed reasons for each returned part

## Compatibility

### Backward Compatibility
- Existing single-product RMA IN operations continue to work
- No changes required to existing warranty claims
- All existing integrations remain functional

### Upgrade Path
- Automatic upgrade of existing warranty claims
- No data migration required
- Seamless transition to enhanced functionality

## Troubleshooting

### Common Issues

1. **Missing Return Lines**
   - **Error**: "Please add at least one return line"
   - **Solution**: Ensure at least one product line is added before creating RMA

2. **Invalid Product Combinations**
   - **Error**: Domain restrictions on lot/serial numbers
   - **Solution**: Ensure lot/serial numbers belong to the selected product

3. **Configuration Issues**
   - **Error**: Missing picking type or location
   - **Solution**: Configure RMA IN settings in Warranty Configuration

### Support
For technical support or questions about the multi-product RMA IN functionality, please refer to the module documentation or contact your system administrator.

## Future Enhancements

Planned improvements for future versions:
- Bulk import of return lines from CSV
- Template-based return configurations
- Enhanced reporting for multi-product returns
- Integration with barcode scanning for faster entry