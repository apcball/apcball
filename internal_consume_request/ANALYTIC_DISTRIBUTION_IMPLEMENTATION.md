# Analytic Distribution Implementation for Internal Consume Request

## Overview
Added analytic distribution tracking to the internal_consume_request module, allowing users to assign analytic accounts to each consumable request line. This feature enables cost tracking and budget management for internal consumable requests.

## Changes Made

### 1. Model Changes (internal_consume_request_line.py)

#### Added Fields:
- **analytic_distribution** (fields.Json):
  - Type: JSON field
  - Required: True (enforced via constraint)
  - Stores analytic account distribution data
  - Format: `{account_id: percentage}`

- **analytic_precision** (fields.Integer):
  - Decimal precision for percentage calculations
  - Automatically retrieves 'Percentage Analytic' precision from system

#### Added Validation:
- **@api.constrains('analytic_distribution')**:
  - Ensures analytic_distribution is not empty
  - Raises ValidationError if no accounts are assigned
  - Message: "Analytic Distribution is mandatory. Please assign an analytic account to each line."

### 2. Request Model Changes (internal_consume_request.py)

#### Enhanced action_submit() Method:
- Added validation to check analytic distribution before submission
- Ensures all lines have analytic distribution assigned
- Raises UserError: "Please enter Analytic Distribution for all items before submitting for approval."

### 3. View Changes (internal_consume_request_views.xml)

#### Updated Tree View for Request Lines:
- Added `analytic_distribution` field to the tree view
- Widget: `analytic_distribution` (specialized widget for percentage-based distribution)
- Required: True (forced at UI level)
- Added `analytic_precision` field as hidden (column_invisible=1)

### 4. Manifest Changes (__manifest__.py)

#### Updated Dependencies:
- Added 'account' module to dependencies for analytic functionality

### 5. Security (ir.model.access.csv)

#### Cleaned Up Access Rules:
- Removed problematic model references that don't exist
- Maintained existing access rules for request and line models
- All security groups have appropriate read/write permissions

## Usage Flow

1. **Employee creates request** → Opens internal.consume.request form
2. **Adds product lines** → Each line appears in the tree view
3. **Assigns analytic distribution** → Uses analytic_distribution widget to select accounts and percentages
4. **Submits for approval** → Validation triggers if analytic distribution is missing
5. **Approval workflow** → Proceeds with complete cost tracking data

## Technical Implementation Details

### Analytic Distribution Field
- **Storage**: JSON format in database
- **Example value**: `{"1": 100.0}` or `{"1": 50.0, "2": 50.0}`
- **Validation**: Both in model constraint and action_submit()

### Widget
- Uses built-in 'analytic_distribution' widget from account module
- Provides user-friendly interface for percentage allocation
- Supports multiple account assignment

### Field Precision
- Automatically fetches decimal precision from "Percentage Analytic"
- Ensures consistent formatting across percentages

## Testing Checklist

- [ ] Create new request and add line items
- [ ] Verify analytic_distribution field is required in tree view
- [ ] Try to submit without analytic distribution → Should fail with error message
- [ ] Assign analytic accounts to each line
- [ ] Submit request → Should succeed
- [ ] Verify data is stored correctly in JSON format
- [ ] Check that analytic precision is correctly retrieved
- [ ] Test with multiple analytic accounts (distributed percentages)

## Module Compatibility

- **Odoo Version**: 17.0
- **Dependencies**: account, base, hr, stock, mail
- **Pattern**: Follows employee_purchase_requisition module implementation

## Reference Implementation
This implementation is based on the employee_purchase_requisition module pattern in the same instance, ensuring consistency across modules.
