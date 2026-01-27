# Sales Margin Approval

Enterprise-grade Odoo 17 module for controlling sales order margin approval with a custom confirmation flow.

## Features

### Margin-Based Approval System
- Define **margin approval rules** for specific sales users
- Configure **margin range lines** with designated approvers for each range
- Support for two approval types:
  - **Any**: One approver is sufficient
  - **All**: All approvers must approve
- Automatic margin calculation and rule application
- Reset approval when prices or discounts change

### Custom Confirmation Flow: "Confirm To SO"
- Sales users must use **"Confirm To SO"** button (not direct confirmation)
- **Confirm To SO** moves order to intermediate state without calling `action_confirm()`
- Admin/Finance users can use standard **"Confirm Sale"** button
- Protection against bypass attempts

### Role-Based Access Control
- **Sales Margin Approvers** - Can approve/reject margin requests
- **Sales Margin Approver User** - Sales users who must follow the Confirm To SO flow

### Approval Workflow
1. Sales user creates quotation with low margin
2. System detects margin rule and shows "Request Margin Approval" button
3. Approvers receive email notifications (Thai language) and mail activities
4. Approvers can approve or reject (with mandatory reason)
5. After approval, sales user clicks "Confirm To SO"
6. Admin/Finance clicks "Confirm Sale" to finalize

### Business States
- **approval_state**: not_required, pending, approved, rejected
- **confirm_flow_state**: draft, confirm_to_so, sale

## Configuration

1. Go to **Sales > Configuration > Margin Approval Rules**
2. Create a new rule:
   - Name the rule
   - Select **Sales Users** who must follow this rule
   - Add **Margin Lines** with:
     - Min/Max margin percentage
     - Approvers for that range
     - Approval type (any/all)

Example:
```
Rule: Sales Team A Margin Control
Sales Users: John, Mary, Peter

Margin Lines:
- 0% to 10% → Approvers: Manager A, Manager B (Type: Any)
- 10% to 15% → Approvers: Team Lead (Type: Any)
```

## Usage Flow

### For Sales Users
1. Create a quotation
2. If margin is low, click **"Request Margin Approval"**
3. Wait for approval
4. After approval, click **"Confirm To SO"** (NOT "Confirm Sale")
5. Notify Admin/Finance to finalize

### For Approvers
1. Receive email notification and activity
2. Review the quotation
3. Click **"Approve Margin"** or **"Reject Margin"**

### For Admin/Finance
1. Open orders in **"Confirm To SO"** state
2. Review and click **"Confirm Sale"**
3. Order moves to **"Sales Order"** state

## Technical Information

### Models
- `margin.approval.rule` - Policy-level configuration
- `margin.approval.rule.line` - Margin ranges with approvers
- `sale.order` (inherit) - Extended with approval logic

### Key Methods
- `action_confirm()` - Overridden to enforce Confirm To SO flow
- `action_confirm_to_so()` - Intermediate state (does NOT confirm order)
- `action_request_margin_approval()` - Send approval request
- `action_approve_margin()` - Approve by authorized user
- `action_reject_margin()` - Reject with reason

### Security Groups
- `group_margin_approval` - Margin approvers
- `group_sales_margin_approver_user` - Sales users using Confirm To SO flow

### Views
- Margin approval rule form with tabs for users and margin lines
- Sale order form with approval/rejection/Confirm To SO buttons
- Tree view with colored badges for states
- Dedicated menus for pending approvals and Confirm To SO orders

## Menu Structure

```
Sales
├── Orders
│   ├── Margin Approvals (pending approvals)
│   └── Confirm To SO (orders waiting for final confirmation)
└── Configuration
    └── Margin Approval Rules
```

## Dependencies
- `sale` - Odoo Sales module
- `mail` - Odoo Mail module

## Multi-Company Support
✅ Fully multi-company ready with company-specific rules

## Non-Intrusive Design
✅ Does NOT modify Odoo core `state` field
✅ Uses separate business state fields
✅ Safe for upgrades and future extensions

## License
LGPL-3

## Author
Your Company
