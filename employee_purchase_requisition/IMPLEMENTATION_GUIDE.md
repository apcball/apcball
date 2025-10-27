# Employee Auto-Selection Implementation Guide

## Overview
This document describes the implementation of automatic employee selection based on the logged-in user for the Purchase Requisition module.

## Problem Statement
Previously, users had to manually select an employee when creating a purchase requisition. This implementation automatically populates the employee field with the employee record linked to the currently logged-in user.

## Implementation Details

### 1. Changes Made to `models/employee_purchase_requisition.py`

#### Added `_default_employee_id()` method
```python
@api.model
def _default_employee_id(self):
    """Get the employee record linked to the current user"""
    employee = self.env.user.employee_id
    return employee.id if employee else False
```

#### Updated `employee_id` field definition
```python
employee_id = fields.Many2one(
    comodel_name='hr.employee',
    string='Employee',
    required=True,
    default=lambda self: self._default_employee_id(),
    help='Select an employee'
)
```

#### Enhanced `create()` method
```python
@api.model
def create(self, vals):
    if vals.get('name', 'New') == 'New':
        vals['name'] = self.env['ir.sequence'].next_by_code('employee.purchase.requisition') or 'New'
    
    # Set employee_id from current user if not provided
    if not vals.get('employee_id'):
        employee = self.env.user.employee_id
        if employee:
            vals['employee_id'] = employee.id
    
    return super().create(vals)
```

#### Added `_onchange_user_id()` method
```python
@api.onchange('user_id')
def _onchange_user_id(self):
    """When user is changed, update employee_id if not set"""
    if self.user_id and not self.employee_id:
        employee = self.user_id.employee_id
        if employee:
            self.employee_id = employee.id
```

### 2. View Configuration
The employee field in `views/employee_purchase_requisition_views.xml` remains configured as:
```xml
<field name="employee_id" readonly="state not in ['new']"/>
```

This ensures:
- Field is editable when creating a new requisition (state = 'new')
- Field becomes read-only after submission (state != 'new')
- Maintains flexibility for users to change the employee if needed

## Features

### ✅ Auto-Population
- Employee field is automatically filled with the current user's employee record
- Works for both new record creation and form initialization

### ✅ Flexibility
- Users can still change the employee field when creating a requisition
- Field becomes read-only after submission to maintain data integrity

### ✅ Error Handling
- Gracefully handles users without linked employee records
- Returns `False` if no employee is linked to the user

### ✅ User Change Support
- When the `user_id` field is changed, the employee field updates if not already set
- Maintains existing employee selection if already chosen

## Testing

### Test Scenarios Covered
1. **Default Employee Selection**: New requisitions auto-populate with current user's employee
2. **Manual Override**: Users can change the employee field when creating
3. **User Change**: Changing user_id updates employee_id if not set
4. **Edge Cases**: Users without linked employees don't cause errors
5. **Field Permissions**: Field respects existing read-only conditions

### Test Script
A test script `test_employee_auto_selection.py` is provided to verify functionality.

## Benefits

1. **Improved User Experience**: Reduces manual data entry
2. **Data Accuracy**: Ensures correct employee association
3. **Flexibility**: Maintains user control while providing automation
4. **Backward Compatibility**: Existing functionality remains intact

## Usage

### For Users
1. Create a new Purchase Requisition
2. The Employee field will be automatically filled with your employee record
3. You can change the employee if needed (only during creation)
4. After submission, the employee field becomes read-only

### For Administrators
- Ensure users have proper employee records linked to their user accounts
- The implementation works with existing security configurations
- No additional configuration required

## Technical Notes

- Uses Odoo's standard `self.env.user.employee_id` relationship
- Implements proper API decorators (`@api.model`, `@api.onchange`)
- Maintains existing field properties and relationships
- Compatible with existing workflows and security rules

## Future Enhancements

Potential improvements could include:
- Configuration option to make employee field always read-only
- Batch update functionality for existing records
- Enhanced logging for audit purposes
- Integration with HR modules for automatic employee creation