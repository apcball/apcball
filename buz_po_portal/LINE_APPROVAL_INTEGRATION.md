# LINE Approval Integration for BUZ Custom PO

## Overview

This document describes the LINE approval integration implemented in the `buz_po_portal` module, which works together with the `line_portal_notification` module to send portal approval links via LINE messaging.

## Features

- **LINE Notification Integration**: Send secure portal approval links to approvers via LINE
- **Multi-stage Workflow**: Supports both review and approval stages
- **Automatic Token Management**: Secure token generation and expiration handling
- **Complete Audit Trail**: Full logging of all LINE notifications and approval actions
- **Thai Language Support**: Customized messages with Thai Baht text conversion

## Prerequisites

1. **Module Dependencies**:
   - `line_portal_notification` module must be installed
   - LINE Official Account with Messaging API enabled
   - Channel Access Token and Channel Secret configured

2. **LINE Configuration**:
   - Go to **Settings > General Settings > LINE Notification**
   - Enter LINE Channel Access Token
   - Enter LINE Channel Secret

3. **User Setup**:
   - Each approver must have their LINE User ID configured
   - Go to **Settings > Users > [User Profile]**
   - Add LINE User ID in the "LINE Notification" section

## How It Works

### 1. Purchase Order Approval Flow

```
Draft → To Review → To Approve → Approved
         ↓              ↓
    [Reviewer]    [Manager]
         ↓              ↓
    LINE Notify   LINE Notify
```

### 2. Sending LINE Approval Request

**When to send:**
- After submitting PO for review (`approval_state = 'to_review'`)
- After reviewer approves and sends to manager (`approval_state = 'to_approve'`)

**How to send:**
1. Open Purchase Order form
2. Click **"Send LINE Approval Request"** button
   - Visible only when `approval_state` is `to_review` or `to_approve`
   - Requires `line_portal_notification.group_line_notification_user` permission

**What happens:**
1. System validates approver has LINE User ID
2. Generates secure, time-limited token (24 hours expiry)
3. Creates portal URL with token
4. Sends customized LINE message to approver
5. Records notification in audit log
6. Updates PO with notification status

### 3. LINE Message Format

For Review Stage:
```
📋 Purchase Order Review Required

PO Number: PO00123
Vendor: ABC Company Ltd.
Amount: 125,000.00 THB
Date: 24/01/2026

👉 Review & approve:
https://yourdomain.com/portal/approve/abc123token

⚠️ This link will expire in 24 hours
```

For Approval Stage:
```
📋 Purchase Order Approval Required

PO Number: PO00123
Vendor: ABC Company Ltd.
Amount: 125,000.00 THB
Date: 24/01/2026

👉 Review & approve:
https://yourdomain.com/portal/approve/abc123token

⚠️ This link will expire in 24 hours
```

### 4. Portal Approval Process

**Approver clicks LINE link:**
1. Opens mobile-friendly portal page
2. Reviews PO details (vendor, amount, items, etc.)
3. Can approve or reject with optional comments
4. Action is immediately recorded
5. Token is invalidated after use
6. PO state is updated automatically

### 5. Approval Actions

**On Approval:**
- If `to_review`: Changes to `to_approve`, sets `reviewed_date`
- If `to_approve`: Changes to `approved`, sets `approval_date`
- Token is marked as used
- Notification posted to chatter

**On Rejection:**
- Changes to `rejected` state
- Token is marked as used
- Notification posted to chatter

## Implementation Details

### Model Inheritance

```python
class PurchaseOrder(models.Model):
    _inherit = ['purchase.order', 'line.approval.mixin']
```

### Key Methods Implemented

1. **`_get_line_approval_approver()`**
   - Returns `approver_id` or `reviewer_id` based on current stage
   
2. **`_get_line_approval_document_name()`**
   - Returns PO number (e.g., "PO00123")
   
3. **`_get_line_approval_amount()`**
   - Returns formatted amount with currency (e.g., "125,000.00 THB")
   
4. **`_get_line_approval_message(portal_url)`**
   - Builds customized LINE message with PO details
   - Includes vendor, amount, date
   - Adds portal link and expiry warning
   
5. **`action_approve()`**
   - Handles approval from portal
   - Updates state based on current approval stage
   - Invalidates token
   - Posts notification to chatter
   
6. **`action_reject()`**
   - Handles rejection from portal
   - Sets state to 'rejected'
   - Invalidates token
   - Posts notification to chatter

### Database Fields

Fields inherited from `line.approval.mixin`:
- `line_notification_sent` (Boolean): Whether LINE was sent
- `line_notification_datetime` (Datetime): When LINE was sent
- `approval_token_id` (Many2one): Link to approval token record

### View Changes

**New Button in Header:**
```xml
<button name="action_send_line_approval_request" 
    string="Send LINE Approval Request" 
    type="object" 
    class="btn-info"
    invisible="approval_state not in ('to_review', 'to_approve')"
    groups="line_portal_notification.group_line_notification_user"/>
```

**New Section in Approval Signatures Page:**
```xml
<group string="LINE Notification Status" invisible="not line_notification_sent">
    <field name="line_notification_sent" readonly="1"/>
    <field name="line_notification_datetime" readonly="1"/>
    <field name="approval_token_id" readonly="1"/>
</group>
```

## Usage Guide

### For Purchasers

1. Create and submit Purchase Order for review
2. Click **"Send LINE Approval Request"** to notify reviewer via LINE
3. Reviewer receives LINE message with portal link
4. After reviewer approves, click again to notify manager
5. Manager receives LINE message with portal link
6. After manager approves, PO is ready to confirm

### For Reviewers/Approvers

1. Receive LINE notification on mobile device
2. Click portal link in message
3. Review PO details on mobile-friendly page
4. Click **Approve** or **Reject**
5. Add optional comments
6. Submit action
7. System updates PO automatically

## Troubleshooting

### Common Issues

**1. "Send LINE Approval Request" button not visible**
- Check: `approval_state` must be `to_review` or `to_approve`
- Check: User has `line_portal_notification.group_line_notification_user` permission

**2. "No approver defined" error**
- Ensure `reviewer_id` or `approver_id` is set on PO
- Check approval workflow is properly configured

**3. "Approver does not have LINE User ID" error**
- Go to Settings > Users
- Edit approver's profile
- Add LINE User ID in "LINE Notification" section

**4. LINE message not received**
- Verify LINE credentials in Settings > General Settings
- Check approver's LINE User ID is correct
- Check internet connection
- Review audit logs for error messages

**5. Portal link expired**
- Default expiry is 24 hours
- Generate new token by clicking "Send LINE Approval Request" again
- Old token will be invalidated

## Security Notes

1. **Token Security**:
   - Cryptographically secure tokens (32 bytes)
   - Single-use tokens (invalidated after approval/rejection)
   - Time-limited (24-hour expiry by default)

2. **Access Control**:
   - Portal approval requires valid token
   - Tokens are specific to approver and document
   - Complete audit trail for compliance

3. **Rate Limiting**:
   - Built-in rate limiting in LINE API service
   - Prevents abuse and spam

## Advanced Customization

### Custom Message Template

Override `_get_line_approval_message()` for custom formatting:

```python
def _get_line_approval_message(self, portal_url):
    self.ensure_one()
    return f"""
🔔 [Your Company] PO Approval

เลขที่ PO: {self.name}
ผู้ขาย: {self.partner_id.name}
ยอดเงิน: {self.amount_total_text_th}

🔗 กดเพื่ออนุมัติ:
{portal_url}

⏰ ลิงก์หมดอายุใน 24 ชั่วโมง
"""
```

### Change Token Expiry

Configure in LINE Portal Notification settings:
- Go to Settings > General Settings > LINE Notification
- Modify "Token Expiry (hours)" parameter

### Custom Approver Logic

Override `_get_line_approval_approver()` for dynamic selection:

```python
def _get_line_approval_approver(self):
    self.ensure_one()
    if self.approval_state == 'to_review':
        return self.reviewer_id
    elif self.approval_state == 'to_approve':
        # Use different approver based on amount
        if self.amount_total > 100000:
            return self.env.ref('base.user_admin')
        return self.approver_id
    return False
```

## Support

For issues or questions:
1. Check module logs: Settings > Technical > Logging
2. Review audit logs: LINE Portal Notification > Approval Audit Logs
3. Check Odoo chatter messages on PO
4. Contact system administrator

## Version History

- **v1.0.0** (2026-01-24): Initial LINE approval integration
  - Basic LINE notification support
  - Multi-stage approval workflow
  - Portal approval interface
  - Thai language message support
