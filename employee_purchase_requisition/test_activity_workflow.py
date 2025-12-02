#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for Activity Notification Workflow in Employee Purchase Requisition

This script demonstrates the activity notification flow:
1. Employee creates PR → Activity sent to Department Head
2. Head approves → Activity sent to Responsible Person
3. Purchase approves → Completion activity created
4. Rejections create appropriate notification activities
"""

import sys
import os

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_activity_workflow():
    """
    Test function to demonstrate the activity workflow
    This would be used in an actual Odoo environment
    """
    
    print("=== Employee Purchase Requisition Activity Workflow Test ===\n")
    
    # Workflow steps demonstration
    workflow_steps = [
        {
            'step': 1,
            'action': 'Employee creates PR and clicks "Confirm"',
            'state_change': 'draft → waiting_head_approval',
            'activity_created': 'Head Approval Required activity sent to manager_user_id',
            'recipient': 'Department Head (manager_user_id)',
            'activity_type': 'mail_activity_type_head_approval'
        },
        {
            'step': 2,
            'action': 'Department Head clicks "Head Approve"',
            'state_change': 'waiting_head_approval → waiting_purchase_approval',
            'activity_created': 'Purchase Processing Required activity sent to user_id',
            'recipient': 'Responsible Person (user_id - เจ้าหน้าที่จัดซื้อ)',
            'activity_type': 'mail_activity_type_purchase_approval'
        },
        {
            'step': 3,
            'action': 'Purchase Department clicks "Purchase Approve"',
            'state_change': 'waiting_purchase_approval → approved',
            'activity_created': 'PR Approved activity sent to original requester',
            'recipient': 'Original Requester (create_uid)',
            'activity_type': 'mail_activity_type_pr_approved'
        },
        {
            'step': 4,
            'action': 'Department Head clicks "Reject"',
            'state_change': 'waiting_head_approval → draft',
            'activity_created': 'PR Rejected activity sent to original requester',
            'recipient': 'Original Requester (create_uid)',
            'activity_type': 'mail_activity_type_pr_rejected'
        },
        {
            'step': 5,
            'action': 'Purchase Department clicks "Reject"',
            'state_change': 'waiting_purchase_approval → draft',
            'activity_created': 'PR Rejected activity sent to original requester',
            'recipient': 'Original Requester (create_uid)',
            'activity_type': 'mail_activity_type_pr_rejected'
        }
    ]
    
    for step in workflow_steps:
        print(f"Step {step['step']}: {step['action']}")
        print(f"  State Change: {step['state_change']}")
        print(f"  Activity Created: {step['activity_created']}")
        print(f"  Recipient: {step['recipient']}")
        print(f"  Activity Type: {step['activity_type']}")
        print("-" * 60)
    
    print("\n=== Key Implementation Details ===")
    print("1. Activity Types Defined:")
    print("   - PR Head Approval Required (3-day deadline)")
    print("   - PR Purchase Processing Required (5-day deadline)")
    print("   - PR Approved (1-day deadline)")
    print("   - PR Rejected (1-day deadline)")
    
    print("\n2. Activity Content Includes:")
    print("   - PR reference number")
    print("   - Department information")
    print("   - Total amount")
    print("   - Purpose/Description")
    print("   - Clear action instructions")
    
    print("\n3. Workflow Integration Points:")
    print("   - action_confirm_requisition(): Creates head approval activity")
    print("   - action_head_approval(): Creates purchase processing activity")
    print("   - action_purchase_approval(): Creates completion activity")
    print("   - action_head_cancel(): Creates rejection activity")
    print("   - action_purchase_cancel(): Creates rejection activity")
    
    print("\n=== Files Modified ===")
    print("1. Created: data/mail_activity_types.xml")
    print("2. Modified: models/employee_purchase_requisition.py")
    print("3. Modified: __manifest__.py")
    
    print("\n=== Testing Instructions ===")
    print("To test the activity workflow in Odoo:")
    print("1. Install/update the employee_purchase_requisition module")
    print("2. Create a new Purchase Requisition as an employee")
    print("3. Click 'Confirm' - check that department head receives activity")
    print("4. Login as department head and approve - check responsible person receives activity")
    print("5. Login as responsible person and approve - check completion activity")
    print("6. Test rejection scenarios at both approval levels")
    
    print("\n=== Activity Notification Workflow Complete ===")

if __name__ == "__main__":
    test_activity_workflow()