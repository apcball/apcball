# Fetch Claim Products Feature Guide

## Overview
The RMA Receive Wizard now includes a "Fetch Claim Products" button that allows users to manually retrieve all products related to a warranty claim, including the main product and any claim lines (parts/consumables).

## Features

### 1. Manual Product Fetching
- **Button**: "Fetch Claim Products" button in the Return Items section
- **Functionality**: Retrieves all claim-related products with one click
- **Visibility**: Only visible when a claim is selected

### 2. Smart Product Selection
The wizard intelligently fetches:
- **Main Product**: The primary product from the warranty claim (the product customer is returning)
- **Lot/Serial Numbers**: Automatically included when available

### 3. Duplicate Prevention
- Checks for existing products in the wizard
- Skips duplicates with appropriate notifications
- Prevents adding the same product multiple times

### 4. Validation & Error Handling
- Validates product availability (active products only)
- Checks if main product is already in existing RMA
- Provides clear feedback messages

## User Workflow

1. **Open RMA Receive Wizard**
   - Navigate to a warranty claim
   - Click "Create RMA IN"

2. **Fetch Products**
   - Click the "Fetch Claim Products" button
   - System retrieves the main product from the warranty claim
   - Product appears in the Return Items list

3. **Review and Edit**
   - Review fetched products and quantities
   - Edit quantities or add notes as needed
   - Add additional products manually if required

4. **Create RMA**
   - Click "Create RMA IN" to complete the process

## Technical Implementation

### Method: `action_fetch_claim_products()`
Located in `warranty_rma_receive_wizard.py`, this method:
- Validates claim selection
- Checks for existing products
- Fetches only the main product from the warranty claim (the product customer is returning)
- Handles duplicates and inactive products
- Provides user notifications

### View Updates
The wizard view (`warranty_rma_receive_wizard_view.xml`) includes:
- New button with download icon
- Proper visibility conditions
- Styled as a stat button for better UX

## Notification Messages

### Success
- "Successfully added the main product from the warranty claim."
- "Successfully added the main product from the warranty claim. Y product(s) were skipped (already in RMA or duplicate)."

### Warning
- "Product Not Added: The main product is already in an existing RMA picking."
- "No Products Added: All products were already added or are inactive."

### Error
- "No warranty claim selected."
- "No products found in this warranty claim."

## Benefits

1. **Efficiency**: One-click product retrieval saves time
2. **Accuracy**: Reduces manual entry errors
3. **Flexibility**: Users can still add/edit products manually
4. **Transparency**: Clear feedback on what was added or skipped

## Testing Scenarios

1. **Normal Case**: Claim with main product
2. **No Main Product**: Claim without main product
3. **Duplicates**: Clicking fetch button multiple times
4. **Inactive Products**: Claims with inactive main product
5. **Existing RMA**: Main product already in RMA

## Future Enhancements

Potential improvements could include:
- Batch fetching for multiple claims
- Customizable product selection
- Integration with inventory availability
- Auto-quantity calculation based on claim type