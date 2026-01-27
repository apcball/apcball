# Analytic Distribution Validation Implementation

## Overview
This implementation enforces that users must enter an Analytic Distribution for all requisition lines before they can submit a purchase requisition for approval.

## Changes Made

### 1. Model Validation (employee_purchase_requisition.py)
Added validation in the `action_confirm_requisition` method to check that all requisition order lines have analytic distribution before allowing submission.

```python
def action_confirm_requisition(self):
    """Function to submit to purchase approval"""
    # Check if all requisition lines have analytic distribution
    for line in self.requisition_order_ids:
        if not line.analytic_distribution:
            raise ValidationError('Please enter Analytic Distribution for all items before submitting for approval.')
    
    # ... rest of the method remains unchanged
```

## How It Works

1. When a user clicks the "Confirm" button to submit a requisition for approval
2. The system iterates through all requisition order lines
3. For each line, it checks if `analytic_distribution` field has a value
4. If any line lacks analytic distribution, a ValidationError is raised
5. The user must fill in the analytic distribution for all items before they can submit

## Validation Logic

The validation checks for:
- Empty dictionary `{}` (default value)
- None values
- Empty strings
- Any falsy value

Only when all lines have a valid analytic distribution (non-empty JSON object) can the requisition be submitted.

## User Experience

- Users will see a clear error message: "Please enter Analytic Distribution for all items before submitting for approval."
- The analytic distribution field is already visible in the form view (line 158-161 in employee_purchase_requisition_views.xml)
- Users with the appropriate group permissions can see and edit the analytic distribution field

## Testing

The validation logic has been tested with various scenarios:
- Empty distribution ✓
- Valid distribution ✓
- None distribution ✓
- Empty string distribution ✓

## Dependencies

This implementation relies on:
- The `analytic` module being installed (already in dependencies)
- The `analytic_distribution` field in the `requisition.order` model
- Proper user permissions for analytic accounting groups