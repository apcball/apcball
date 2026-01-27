# Employee Purchase Requisition - Edit Lock and Cancel Functionality Implementation Plan

## Overview
This implementation plan outlines the changes needed to add edit lock functionality for documents waiting approval and cancel functionality that returns documents to draft state for re-editing.

## Current State Analysis
- Current states: new, waiting_head_approval, waiting_purchase_approval, approved, purchase_order_created, received, cancelled
- Current workflow: new → waiting_head_approval → waiting_purchase_approval → approved → purchase_order_created → received
- Current rejection: documents go to 'cancelled' state when rejected

## Required Changes

### 1. Model Changes (`employee_purchase_requisition.py`)

#### State Field Updates
- Replace 'new' with 'draft' in state selection
- Update default state from 'new' to 'draft'
- State flow: draft → waiting_head_approval → waiting_purchase_approval → approved → purchase_order_created → received

#### New Methods
- `action_cancel_requisition()` - Cancel document and return to draft (only for original requester)
- `action_head_cancel()` - Modify to return to draft instead of cancelled
- `action_purchase_cancel()` - Modify to return to draft instead of cancelled

#### Permission Checks
- Add method to check if current user is original requester
- Implement edit lock logic (only allow edits in draft state)

### 2. View Changes (`employee_purchase_requisition_views.xml`)

#### Form View Updates
- Update statusbar to show 'draft' instead of 'new'
- Add cancel buttons for waiting approval states
- Update readonly conditions for fields (readonly when not in draft state)
- Update button visibility conditions

#### Button Additions
- Cancel button for waiting_head_approval state (visible only to original requester)
- Cancel button for waiting_purchase_approval state (visible only to original requester)

#### Field Permissions
- Make fields readonly when state is not 'draft'
- Allow requisition_order_ids editing only in draft state

### 3. Security and Access Control
- Ensure only original requester can cancel documents
- Maintain existing approval permissions
- Enforce edit locks through view permissions

## Implementation Workflow

### Phase 1: Model Updates
1. Update state field definition
2. Add new cancel methods
3. Modify existing rejection methods
4. Add permission check methods

### Phase 2: View Updates
1. Update form view with new buttons
2. Modify readonly conditions
3. Update statusbar
4. Test button visibility

### Phase 3: Testing
1. Test complete workflow
2. Verify edit locks work correctly
3. Test cancel functionality
4. Verify permissions are enforced

## Expected Behavior After Implementation

### Draft State
- All fields editable
- Submit button visible
- No cancel button needed

### Waiting Head Approval
- All fields readonly
- Head approve/reject buttons visible
- Cancel button visible only to original requester
- Cancel returns document to draft state

### Waiting Purchase Approval
- All fields readonly
- Purchase approve/reject buttons visible
- Cancel button visible only to original requester
- Cancel returns document to draft state

### Rejection Behavior
- Head rejection returns to draft state
- Purchase rejection returns to draft state
- Original requester can then edit and resubmit

## Technical Considerations

### State Transitions
```
draft → waiting_head_approval (submit)
waiting_head_approval → waiting_purchase_approval (approve)
waiting_head_approval → draft (cancel/reject)
waiting_purchase_approval → approved (approve)
waiting_purchase_approval → draft (cancel/reject)
```

### Permission Matrix
| State | Requester | Head | Purchase |
|-------|-----------|------|----------|
| draft | Edit | View | View |
| waiting_head_approval | Cancel | Approve/Reject | View |
| waiting_purchase_approval | Cancel | View | Approve/Reject |
| approved+ | View | View | View |

### Field Access Control
- Use `attrs="{'readonly': [('state', '!=', 'draft')]}"` for form fields
- Use `readonly="state not in ['draft']"` for specific fields
- Maintain existing group permissions for approval buttons

## Testing Checklist

### Basic Workflow
- [ ] Create new requisition (starts in draft)
- [ ] Edit all fields in draft state
- [ ] Submit requisition (moves to waiting_head_approval)
- [ ] Verify fields are readonly
- [ ] Cancel requisition (returns to draft)
- [ ] Edit and resubmit
- [ ] Complete approval workflow

### Permission Testing
- [ ] Verify only requester can cancel
- [ ] Verify approvers cannot edit in waiting states
- [ ] Verify rejection returns to draft
- [ ] Test with different user roles

### Edge Cases
- [ ] Cancel after partial approval
- [ ] Multiple cancel/reject cycles
- [ ] Permission boundary testing