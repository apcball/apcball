# Testing Guide for Cost Field Security Implementation

## Overview
This guide provides step-by-step instructions to test the security implementation that hides Unit cost and Total value fields from users without the "Stock Cost Viewer" permission.

## Prerequisites
1. Install or update the buz_stock_current_report module
2. Have access to Odoo with administrator rights
3. Create test users with different permission levels

## Test Scenarios

### 1. Test with Regular User (No Cost Access)

#### Setup:
- Create a new user or use an existing stock user
- Ensure the user is NOT in the "Stock Cost Viewer" group
- Assign the user to "Stock User" group for basic access

#### Expected Results:
1. **Tree View**: Unit Cost and Total Value columns should not be visible
2. **Form View**: Unit Cost and Total Value fields should not be visible
3. **Kanban View**: Cost badges and Unit Cost information should not be visible
4. **Search Filters**: "High Value" filter should not be visible
5. **Excel Export**: Excel file should not contain Unit Cost and Total Value columns

#### Steps:
1. Login as the regular user
2. Navigate to Inventory → Current Stock Report → Current Stock View
3. Verify the tree view doesn't show cost columns
4. Click on any record to open form view
5. Verify cost fields are not visible
6. Switch to Kanban view
7. Verify cost information is not displayed
8. Try the search filters - "High Value" should not be available
9. Use the Export to Excel feature
10. Open the exported file and verify cost columns are absent

### 2. Test with Cost Viewer User

#### Setup:
- Create a new user or use an existing user
- Add the user to the "Stock Cost Viewer" group
- Ensure the user also has basic stock access

#### Expected Results:
1. **Tree View**: Unit Cost and Total Value columns should be visible
2. **Form View**: Unit Cost and Total Value fields should be visible
3. **Kanban View**: Cost badges and Unit Cost information should be visible
4. **Search Filters**: "High Value" filter should be visible and functional
5. **Excel Export**: Excel file should contain Unit Cost and Total Value columns

#### Steps:
1. Login as the cost viewer user
2. Navigate to Inventory → Current Stock Report → Current Stock View
3. Verify the tree view shows cost columns
4. Click on any record to open form view
5. Verify cost fields are visible
6. Switch to Kanban view
7. Verify cost information is displayed
8. Try the search filters - "High Value" should be available
9. Use the "High Value" filter and verify it works
10. Use the Export to Excel feature
11. Open the exported file and verify cost columns are present with data

### 3. Test with Administrator

#### Setup:
- Login as administrator

#### Expected Results:
- All functionality should work as expected
- Administrator should be able to assign users to the "Stock Cost Viewer" group

#### Steps:
1. Login as administrator
2. Navigate to Settings → Users & Companies → Users
3. Select any user
4. Verify the "Stock Cost Viewer" group is available in the Access Rights tab
5. Test adding/removing the group from users

## Additional Tests

### Group Assignment Test
1. Go to Settings → Users & Companies → Groups
2. Search for "Stock Cost Viewer"
3. Verify the group exists with correct description
4. Check the group is under the Inventory category

### Performance Test
1. Test with large datasets to ensure the security checks don't significantly impact performance
2. Verify that switching between views is smooth

### Edge Cases
1. Test with users who have multiple groups
2. Test with inherited groups
3. Test after module upgrade

## Troubleshooting

### Common Issues and Solutions

1. **Cost fields still visible for regular users**
   - Check if the groups attribute is correctly applied in all views
   - Verify the user is not in the cost viewer group
   - Restart Odoo server after changes

2. **Cost fields not visible for authorized users**
   - Verify the user is properly added to the "Stock Cost Viewer" group
   - Check if the group has proper access rights
   - Clear browser cache and reload

3. **Excel export issues**
   - Check the user permission logic in the XLSX report
   - Verify the SQL query in the wizard
   - Ensure the group reference is correct

4. **Search filter issues**
   - Verify the groups attribute on the filter
   - Check for any syntax errors in the XML

## Verification Checklist

- [ ] Regular users cannot see cost fields in tree view
- [ ] Regular users cannot see cost fields in form view
- [ ] Regular users cannot see cost fields in kanban view
- [ ] Regular users cannot use "High Value" filter
- [ ] Regular users get Excel export without cost columns
- [ ] Cost viewers can see cost fields in tree view
- [ ] Cost viewers can see cost fields in form view
- [ ] Cost viewers can see cost fields in kanban view
- [ ] Cost viewers can use "High Value" filter
- [ ] Cost viewers get Excel export with cost columns
- [ ] Administrators can assign users to the cost viewer group
- [ ] Performance is acceptable with security checks
- [ ] No error messages in logs related to field access

## Final Notes

After completing all tests, ensure that:
1. The implementation meets all security requirements
2. The user experience is smooth for both regular and authorized users
3. The documentation is updated with any findings
4. The module is ready for production deployment