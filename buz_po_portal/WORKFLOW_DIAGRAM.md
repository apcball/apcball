# LINE Approval Workflow Diagram

## Purchase Order Approval Flow with LINE Notification

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PURCHASE ORDER APPROVAL FLOW                     │
└─────────────────────────────────────────────────────────────────────┘

┌──────────┐
│  Draft   │  ← User creates PO
└────┬─────┘
     │
     │ Click "Send for Review"
     │ (Opens wizard, captures signature)
     ↓
┌──────────────────┐
│  To Review       │  ← Reviewer assigned
└────┬─────────────┘
     │
     │ ┌─────────────────────────────────────────────┐
     │ │ Click "Send LINE Approval Request"          │
     │ └─────────────────────────────────────────────┘
     │           │
     │           ├─→ Generate Token
     │           ├─→ Create Portal URL
     │           └─→ Send LINE Message
     │                    ↓
     │           ┌────────────────────┐
     │           │   📱 LINE Message   │
     │           │                    │
     │           │ 📋 PO Review Req   │
     │           │ PO: PO00123        │
     │           │ Vendor: ABC Ltd    │
     │           │ Amount: 125K THB   │
     │           │                    │
     │           │ 👉 [Portal Link]   │
     │           └────────────────────┘
     │                    ↓
     │           ┌────────────────────┐
     │           │  Reviewer clicks   │
     │           │  Opens Portal Page │
     │           └────────────────────┘
     │                    ↓
     │           ┌────────────────────┐
     │           │  Reviews Details   │
     │           │  Clicks "Approve"  │
     │           └────────────────────┘
     │
     │ OR: Click "Check & Sign" in Odoo
     │ (Opens wizard, captures signature)
     ↓
┌──────────────────┐
│  To Approve      │  ← Manager assigned
└────┬─────────────┘
     │
     │ ┌─────────────────────────────────────────────┐
     │ │ Click "Send LINE Approval Request"          │
     │ └─────────────────────────────────────────────┘
     │           │
     │           ├─→ Generate New Token
     │           ├─→ Create Portal URL
     │           └─→ Send LINE Message
     │                    ↓
     │           ┌────────────────────┐
     │           │   📱 LINE Message   │
     │           │                    │
     │           │ 📋 PO Approval Req │
     │           │ PO: PO00123        │
     │           │ Vendor: ABC Ltd    │
     │           │ Amount: 125K THB   │
     │           │                    │
     │           │ 👉 [Portal Link]   │
     │           └────────────────────┘
     │                    ↓
     │           ┌────────────────────┐
     │           │  Manager clicks    │
     │           │  Opens Portal Page │
     │           └────────────────────┘
     │                    ↓
     │           ┌────────────────────┐
     │           │  Reviews Details   │
     │           │  Clicks "Approve"  │
     │           └────────────────────┘
     │
     │ OR: Click "Approve & Sign" in Odoo
     │ (Opens wizard, captures signature)
     ↓
┌──────────┐
│ Approved │  ← Ready to confirm
└────┬─────┘
     │
     │ Click "Confirm Order"
     ↓
┌──────────┐
│ Purchase │  ← PO confirmed, creates receipts
└──────────┘


═══════════════════════════════════════════════════════════════════

REJECTION FLOW:

At any stage (To Review or To Approve):
     │
     │ Portal: Click "Reject"
     │ OR: Manual action in Odoo
     ↓
┌──────────┐
│ Rejected │  ← PO rejected
└────┬─────┘
     │
     │ Click "Reset Approval"
     ↓
┌──────────┐
│  Draft   │  ← Back to draft, can edit and resubmit
└──────────┘


═══════════════════════════════════════════════════════════════════

TOKEN LIFECYCLE:

┌─────────────────────┐
│  Generate Token     │
│  - 32 bytes secure  │
│  - 24h expiry       │
│  - State: active    │
└──────┬──────────────┘
       │
       ├──→ LINE Message Sent
       │    (Token linked to PO)
       │
       ├──→ Portal Accessed
       │    (Token validated)
       │
       └──→ Action Taken
            (Approve/Reject)
                 ↓
       ┌─────────────────────┐
       │  Invalidate Token   │
       │  - State: used      │
       │  - Cannot reuse     │
       └─────────────────────┘


═══════════════════════════════════════════════════════════════════

SECURITY LAYERS:

1. Token Generation
   └─→ Cryptographically secure (secrets.token_urlsafe)

2. Token Validation
   ├─→ Check token exists
   ├─→ Check not expired (24h)
   ├─→ Check state = active
   └─→ Check matches approver

3. Portal Access
   ├─→ Token required in URL
   ├─→ No login required
   └─→ Single-use only

4. Audit Trail
   ├─→ Log notification sent
   ├─→ Log portal access
   ├─→ Log approval action
   └─→ Immutable records


═══════════════════════════════════════════════════════════════════

INTEGRATION POINTS:

┌─────────────────────────────────────────────────────────────────┐
│                        buz_po_portal                            │
│                                                                 │
│  ┌──────────────┐      ┌──────────────┐     ┌──────────────┐  │
│  │ PO Model     │─────▶│ LINE Mixin   │────▶│ Portal Views │  │
│  │              │      │ Methods      │     │              │  │
│  │ - Fields     │      │              │     │ - Review     │  │
│  │ - States     │      │ - Approver   │     │ - Approve    │  │
│  │ - Workflow   │      │ - Message    │     │ - Reject     │  │
│  └──────────────┘      │ - Actions    │     └──────────────┘  │
│                        └──────┬───────┘                        │
└───────────────────────────────┼────────────────────────────────┘
                                │
                                │ Inherits
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                  line_portal_notification                       │
│                                                                 │
│  ┌──────────────┐      ┌──────────────┐     ┌──────────────┐  │
│  │ LINE API     │      │ Token Mgmt   │     │ Audit Log    │  │
│  │              │      │              │     │              │  │
│  │ - Send MSG   │      │ - Generate   │     │ - Track      │  │
│  │ - Push API   │      │ - Validate   │     │ - History    │  │
│  │ - Webhook    │      │ - Expire     │     │ - Security   │  │
│  └──────────────┘      └──────────────┘     └──────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ External API
                                ↓
                        ┌────────────────┐
                        │  LINE Platform │
                        │                │
                        │ - Messaging    │
                        │ - Push Service │
                        │ - User Mgmt    │
                        └────────────────┘
```

## Key Components

### 1. Purchase Order States
- `draft` → `to_review` → `to_approve` → `approved`
- `rejected` (can reset to draft)

### 2. LINE Notification Trigger Points
- After "Send for Review" → Can send to Reviewer
- After "Check & Sign" → Can send to Manager
- Manual click on "Send LINE Approval Request" button

### 3. Portal Actions
- View PO details (vendor, amount, items, terms)
- Approve (with optional comment)
- Reject (with optional comment)

### 4. Automatic Updates
- PO state changes based on approval
- Token invalidated after use
- Audit log updated
- Chatter notification posted

### 5. Data Flow
```
User Action → Token Generation → LINE Message → 
Portal View → Approval Action → State Update → 
Token Invalidation → Audit Log
```
