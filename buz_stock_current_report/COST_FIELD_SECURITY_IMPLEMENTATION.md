# Cost Field Security Implementation

## Overview
This document outlines the implementation of security controls to hide Unit cost and Total value fields in the Current Stock View report module. The implementation uses a security group-based approach to control visibility of these sensitive financial fields.

## Security Model
A new security group "Stock Cost Viewer" will be created to control access to cost information:
- Users in this group can see Unit cost and Total value fields
- Users not in this group will have these fields hidden from all views
- Only administrators can assign users to this group

## Implementation Details

### 1. Security Group Creation
- Create a new group: `group_stock_cost_viewer`
- Category: Inventory
- Description: "Users who can view cost information in stock reports"

### 2. Field Visibility Control
The following fields will be controlled by the security group:
- `unit_cost` (Unit Cost)
- `total_value` (Total Value)

### 3. Views Modification
All views will be updated to use the `groups` attribute:
- Tree view: Add groups attribute to cost fields
- Form view: Add groups attribute to cost fields
- Kanban view: Add groups attribute to cost fields
- Search view: Remove "High Value" filter (depends on total_value)

### 4. Excel Export Control
The Excel export will be modified to:
- Check if the current user belongs to the cost viewer group
- Include cost columns only if user has permission
- Adjust headers and data accordingly

### 5. Model Updates
The model will be updated to:
- Add groups parameter to unit_cost and total_value fields
- Ensure proper access control at the field level

## Files to Modify

1. `security/stock_current_report_security.xml`
   - Add new security group definition
   - Add access rights for the new group

2. `views/stock_current_report_views.xml`
   - Add groups attribute to cost fields in tree view
   - Add groups attribute to cost fields in form view
   - Add groups attribute to cost fields in kanban view
   - Remove "High Value" filter from search view

3. `models/stock_current_report.py`
   - Add groups parameter to unit_cost and total_value fields

4. `report/stock_current_report_xlsx.py`
   - Check user permissions before including cost columns
   - Conditionally include/exclude cost data based on permissions

5. `wizard/stock_current_export_wizard.py`
   - Update SQL query to conditionally include cost fields
   - Check user permissions before returning cost data

## Implementation Steps

1. Create the security group and access rights
2. Update model field definitions with groups parameter
3. Modify all views to use groups attribute
4. Update Excel export logic
5. Update wizard SQL queries
6. Test with different user roles

## Testing Strategy

1. Test with regular user (no cost access):
   - Verify cost fields are hidden in all views
   - Verify Excel export doesn't include cost columns
   - Verify search filters don't include cost-based options

2. Test with cost viewer user:
   - Verify cost fields are visible in all views
   - Verify Excel export includes cost columns
   - Verify all functionality works correctly

3. Test with administrator:
   - Verify ability to assign users to cost viewer group
   - Verify all functionality works correctly

## Security Considerations

- Cost information is sensitive financial data
- Only authorized personnel should have access
- The implementation follows Odoo's security best practices
- Field-level security ensures data protection at all levels

## Impact Assessment

- Regular users will have a cleaner interface without cost information
- Authorized users will continue to have full access to cost data
- No existing functionality will be broken
- Performance impact is minimal