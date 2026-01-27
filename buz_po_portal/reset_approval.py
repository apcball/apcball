#!/usr/bin/env python3
"""
Script to reset approval state for testing
Usage: Run this from Odoo shell or modify the PO record directly
"""

# Example for Odoo shell:
# odoo-bin shell -d your_database_name

# Then in the shell:
"""
# Find the PO by token or name
token = 'fqzEl61Ad8rbtQVah0VjRUtQt5RHWz7J3WDBjlXDZE'
po = env['purchase.order'].search([('approval_token', '=', token)], limit=1)

# Or by name
# po = env['purchase.order'].search([('name', '=', 'PO00123')], limit=1)

if po:
    print(f"Found PO: {po.name}")
    print(f"Current state: approval_state={po.approval_state}, approval_token_expired={po.approval_token_expired}")
    
    # Reset approval
    po.action_reset_approval_draft()
    print("Approval reset to draft")
    
    # Re-submit for approval to generate new token
    po.action_submit_for_approval()
    print(f"Re-submitted for approval. New URL: {po.get_public_approval_url()}")
else:
    print("PO not found")
"""

# Or direct SQL (USE WITH CAUTION):
"""
UPDATE purchase_order 
SET approval_state = 'to_approve',
    approval_signature = NULL,
    approval_date = NULL,
    approval_token_expired = FALSE
WHERE approval_token = 'your_token_here';
"""
