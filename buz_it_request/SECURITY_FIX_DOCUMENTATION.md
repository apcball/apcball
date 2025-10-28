# Security Fix for IT Procurement Request Module

## Issues Fixed

### Issue 1: Users unable to add products to procurement lines
Users were unable to add products to IT procurement request lines because the security configuration only provided read access to the `it.procurement.line` model, preventing users from creating or modifying procurement lines.

### Issue 2: IT Manager cannot approve requests
IT Managers were unable to approve procurement requests due to access issues with the approval note field.

## Root Causes

### Issue 1 Root Cause
The security configuration in `security/ir.model.access.csv` only granted read access (perm_read=1) to the `it.procurement.line` model for `base.group_user`, with no write, create, or delete permissions.

### Issue 2 Root Cause
The approval note field in the view was not properly configured for edit access by IT Managers during the approval state.

## Solution Implemented

### 1. Updated Access Rights (security/ir.model.access.csv)
Replaced the single access rule with four specific access rules for each user group:

- **IT Requesters** (`group_it_requester`): Full CRUD access to procurement lines for their own requests
- **IT Users** (`group_it_user`): Full CRUD access to all procurement lines
- **IT Managers** (`group_it_manager`): Full CRUD access to all procurement lines
- **IT Manager Approvers** (`group_it_manager_approver`): Full CRUD access to procurement lines within their department

### 2. Added Record Rules (security/security.xml)
Added three record rules to ensure proper data access control:

- **Own Records Rule**: IT Requesters can only access procurement lines from their own requests
- **Department Records Rule**: IT Manager Approvers can only access procurement lines from requests within their department
- **All Records Rule**: IT Users and IT Managers can access all procurement lines

### 3. Updated View Configuration (views/it_request_procurement_views.xml)
Modified the Approval tab to:
- Only show when the request is not in draft state
- Make the approval note field editable only during the approval state (`to_manager_approve`)
- Made the approval note field required when in approval state to ensure proper validation
- Updated syntax to be compatible with Odoo 17 (replaced `attrs` with direct `invisible` and `readonly` attributes)

### 4. Enhanced Approval Method (models/it_request_procurement.py)
Modified the `action_manager_approve` method to:
- Add `ensure_one()` to ensure we're working with a single record
- Provide clearer error message when approval note is missing
- Ensure the form is properly saved before validation

### 5. Fixed Purchase Order Creation (models/it_request_procurement.py)
Modified the `action_create_pr` method to:
- Remove the invalid `it_request_procurement_id` field reference that doesn't exist on purchase.order model
- Keep the `origin` field to maintain traceability back to the procurement request

## Files Modified
1. `buz_it_request/security/ir.model.access.csv` - Updated access rights for procurement lines
2. `buz_it_request/security/security.xml` - Added record rules for procurement lines
3. `buz_it_request/views/it_request_procurement_views.xml` - Fixed approval note field access and Odoo 17 compatibility
4. `buz_it_request/models/it_request_procurement.py` - Enhanced approval method and fixed purchase order creation

## Testing Instructions
To verify the fixes:

1. Upgrade the `buz_it_request` module
2. Test as IT Requester:
   - Create a new IT Procurement Request
   - Verify that you can add products to procurement lines
   - Submit for approval
3. Test as IT Manager:
   - Open a request awaiting approval
   - Verify you can see the Approval tab
   - Verify you can add an approval note
   - Verify you can approve the request
4. Test as IT User:
   - Verify you can access and modify procurement lines
5. Verify that users can only see/edit procurement lines they have access to based on their role

## Security Considerations
- The access rights are now properly aligned with the existing access patterns for other IT request models
- Record rules ensure data isolation between departments and users
- All user groups that need to interact with procurement requests now have appropriate access to the lines
- The approval note field is properly secured and only editable during the appropriate workflow state

## Impact
- Users can now successfully add products to IT procurement request lines
- IT Managers can now approve procurement requests by adding approval notes
- The complete approval workflow for IT procurement requests can now function as intended
- No breaking changes to existing functionality