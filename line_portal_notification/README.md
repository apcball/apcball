# LINE Portal Notification

Odoo 17 module for sending LINE notifications with secure portal links for document approval.

## Features

- **Secure Token Generation**: Generate cryptographically secure, single-use tokens for portal access
- **LINE Messaging API Integration**: Send push messages via LINE Messaging API
- **Portal Approval Pages**: Clean, mobile-friendly approval interface
- **Complete Audit Trail**: Immutable logs for all approval actions
- **Rate Limiting**: Protection against abuse
- **Configurable Expiry**: Set custom token expiration periods

## Installation

1. Copy the `line_portal_notification` folder to your Odoo addons directory
2. Update the apps list in Odoo
3. Install the module from Apps menu

## Configuration

### LINE Credentials

1. Create a LINE Official Account at [LINE Developers Console](https://developers.line.biz/)
2. Create a Messaging API channel
3. Get your Channel Access Token and Channel Secret
4. In Odoo, go to **Settings > General Settings > LINE Notification**
5. Enter your credentials

### User Setup

For each approver:
1. Go to **Settings > Users**
2. Edit the user profile
3. Add their LINE User ID in the "LINE Notification" section

## Usage

### Adding LINE Approval to Your Model

1. **Inherit the mixin** in your model:

```python
from odoo import models, fields

class YourModel(models.Model):
    _name = 'your.model'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'line.approval.mixin']
    
    approver_id = fields.Many2one('res.users', string='Approver')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting_approval', 'Waiting Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ])
    
    def _get_line_approval_approver(self):
        """Return the approver user."""
        return self.approver_id
    
    def action_approve(self):
        """Handle approval action."""
        self.state = 'approved'
        self._invalidate_approval_token('approved')
    
    def action_reject(self):
        """Handle rejection action."""
        self.state = 'rejected'
        self._invalidate_approval_token('rejected')
```

2. **Add the button** to your form view:

```xml
<button name="action_send_line_approval_request"
        string="Send LINE Approval Request"
        type="object"
        class="btn-primary"
        invisible="state != 'waiting_approval'"
        groups="line_portal_notification.group_line_notification_user"/>
```

### Customizing the LINE Message

Override `_get_line_approval_message()` in your model:

```python
def _get_line_approval_message(self, portal_url):
    return f"""
📄 Purchase Order Approval Required

Ref: {self.name}
Vendor: {self.partner_id.name}
Amount: {self.amount_total:,.2f} {self.currency_id.name}

👉 Review & approve:
{portal_url}
"""
```

## Security

- Tokens are generated using Python's `secrets.token_urlsafe(32)`
- Tokens are single-use and automatically invalidated after action
- Rate limiting prevents brute-force attacks
- All actions are logged with IP address and user agent
- Audit logs are immutable (cannot be edited or deleted)

## Models

| Model | Description |
|-------|-------------|
| `approval.token` | Stores approval tokens with expiry |
| `approval.audit.log` | Immutable audit trail |
| `line.approval.mixin` | Abstract model to inherit |
| `line.api.service` | LINE Messaging API wrapper |

## API Reference

### LineApprovalMixin Methods

| Method | Description |
|--------|-------------|
| `action_send_line_approval_request()` | Main button action to send LINE notification |
| `_get_line_approval_approver()` | Override to return the approver user |
| `_get_line_approval_document_name()` | Override to customize document name |
| `_get_line_approval_amount()` | Override to customize amount display |
| `_get_line_approval_message(portal_url)` | Override to customize LINE message |
| `action_approve()` | Must be implemented - handle approval |
| `action_reject()` | Must be implemented - handle rejection |
| `_invalidate_approval_token(action)` | Call after approve/reject to invalidate token |

### LineApiService Methods

| Method | Description |
|--------|-------------|
| `send_push_message(line_user_id, message)` | Send text message |
| `send_flex_message(line_user_id, alt_text, flex_contents)` | Send rich Flex message |
| `validate_access_token()` | Validate configured access token |

## Troubleshooting

### "LINE User ID is not configured"
- Add LINE User ID to the approver's user profile

### "LINE API authentication failed"
- Check your Channel Access Token in Settings

### "Cannot send message: User has blocked..."
- The approver needs to add/unblock the LINE Official Account

## License

LGPL-3

## Author

Your Company
