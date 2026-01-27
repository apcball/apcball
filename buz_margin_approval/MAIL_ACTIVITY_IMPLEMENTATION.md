# Mail Activity Notification Implementation for buz_margin_approval

## Overview
This document describes the implementation of mail activity notifications for User Approvers in the buz_margin_approval module.

## Changes Made

### 1. Updated `__manifest__.py`
- **Changed**: Added `'mail'` to the `depends` list
- **Purpose**: Enable mail activity functionality for the module
- **Line**: 14

```python
'depends': ['sale_management', 'sale_margin', 'sales_team', 'mail'],
```

### 2. Updated `models/sale_order.py`

#### A. Modified `action_request_margin_approval()` method
- **Change**: Added call to `_create_margin_approval_activities()` to create mail activities for each approver
- **Location**: Around line 77
- **Effect**: When a margin approval is requested, mail activities are automatically created for all assigned approvers

```python
# Create mail activities for approvers
self._create_margin_approval_activities()
```

#### B. Modified `action_approve_margin()` method
- **Change**: Added call to `_mark_margin_approval_activities_done()` to mark activities as complete
- **Location**: Around line 98
- **Effect**: When a margin is approved, all related mail activities are marked as done

```python
# Mark mail activities as done
self._mark_margin_approval_activities_done()
```

#### C. Added `_create_margin_approval_activities()` method
- **Purpose**: Creates a "To Do" mail activity for each margin approver
- **Functionality**:
  - Deletes old pending activities to avoid duplicates
  - Creates new activity for each approver with:
    - Activity type: "To Do"
    - Summary: "Approve Sales Order Margin: [SO Number]"
    - Note: Contains order details (customer, margin %, amount, sales person)
    - Deadline: Current date
  - Uses Odoo's mail activity reference: `mail.mail_activity_data_todo`

#### D. Added `_mark_margin_approval_activities_done()` method
- **Purpose**: Marks all pending margin approval activities as done when order is approved
- **Functionality**:
  - Searches for all pending "To Do" activities for the sale order
  - Marks them as done with feedback: "Margin Approved"

#### E. Added `_mark_margin_approval_activities_rejected()` method
- **Purpose**: Marks all pending margin approval activities as done with rejection reason when order is rejected
- **Parameters**: `rejection_reason` (optional) - the reason for rejection
- **Functionality**:
  - Searches for all pending "To Do" activities for the sale order
  - Marks them as done with feedback including the rejection reason

### 3. Updated `wizard/margin_rejection_wizard.py`

#### Modified `action_reject()` method
- **Change**: Added call to `_mark_margin_approval_activities_rejected()` with rejection reason
- **Location**: End of method, before closing the wizard
- **Effect**: When a margin is rejected, all related mail activities are marked as done with the rejection reason

```python
# Mark mail activities as rejected with reason
sale_order._mark_margin_approval_activities_rejected(self.rejection_reason)
```

## User Experience Flow

1. **Request for Approval**: When a user clicks "Request Margin Approval" on a low-margin sales order:
   - Mail activities are automatically created for all assigned approvers
   - Approvers see a "To Do" activity in their activity widget
   - Each activity contains key order details

2. **Approval**: When an approver clicks "Approve Margin":
   - The activity is automatically marked as done
   - Feedback message "Margin Approved" is recorded

3. **Rejection**: When an approver clicks "Reject Margin" and provides a reason:
   - The activity is automatically marked as done
   - Feedback message includes the rejection reason

## Technical Details

- **Activity Type**: Uses Odoo's built-in "To Do" activity type
- **Deadline**: Set to the current date
- **Model**: Activities are linked to `sale.order` model
- **User Assignment**: Activities are assigned to users in the margin approval rule

## Benefits

✅ Approvers receive mail activity notifications in their Odoo inbox  
✅ Activities provide quick access to order details  
✅ Activities are automatically marked as done when approved/rejected  
✅ Rejection reasons are tracked in activity feedback  
✅ Integrates seamlessly with Odoo's mail system  
✅ No additional configuration needed - works automatically

## Compatibility

- **Odoo Version**: 17.0
- **Dependencies**: 
  - sale_management
  - sale_margin
  - sales_team
  - mail (newly added)

## Future Enhancements

Potential improvements for future versions:
- Add automatic email reminders for pending activities
- Allow customization of activity deadlines per rule
- Add activity type selection in margin approval rules
- Track activity history for compliance/audit purposes
