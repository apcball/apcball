# prompt.md

You are a senior Odoo 17 architect and developer.

Your task is to UPGRADE an existing custom module named:

`internal_consume_request`

Do NOT create a new module from scratch.

You must inherit and improve the existing module while preserving backward compatibility.

---

# PROJECT GOAL

Upgrade the current Internal Consumable Request system into an enterprise-grade warehouse issue system with:

1. Smart Mobile Barcode Picking
2. Actual Issued Quantity Control
3. Partial Fulfillment Support
4. Dual Signature Capture
5. Real Stock Transfer Based on Actual Qty
6. Better Status Tracking
7. Audit Trail

The existing workflow already has:

Draft → To Approve → Approved → Done / Rejected

Keep existing features working.

---

# EXISTING MODULE CONTEXT

Current module contains:

## Models

### internal.consume.request

Header document for internal requisition.

### internal.consume.request.line

Requested item lines.

### stock.picking inheritance

Used to mark request as done when transfer validates.

## Existing Features

- Employee creates request
- Manager approves
- Stock validation
- Auto create picking
- Analytic distribution required
- Auto reject if insufficient stock

---

# NEW FEATURES TO DEVELOP

---

# 1. MOBILE BARCODE ISSUE FLOW

After request is Approved:

Warehouse user can process issue from mobile interface.

Create new menu:

Inventory > Barcode > Internal Consume Requests

Mobile page must support:

## Step 1: Scan Request

Scan QR / Barcode of request number

Example:

REQ00045

Open request issue screen.

---

## Step 2: Issue Screen

Display all request lines.

For each line show:

- Product
- Requested Qty
- Available Qty
- Issued Qty (editable)
- Checkbox select to issue

Example:

Mouse Logitech
Requested: 5
Issued: [3]

Keyboard Dell
Requested: 2
Issued: [2]

HDMI Cable
Requested: 4
Issued: [0]

Warehouse can:

- edit issued qty
- scan product barcode
- auto increment qty
- deselect lines

---

# 2. ACTUAL ISSUE QUANTITY

Add fields on request line:

```python
issued_qty = fields.Float()
remaining_qty = fields.Float(compute=...)
is_issued = fields.Boolean()
Rules:

issued_qty <= requested_qty
issued_qty >= 0

remaining_qty = requested_qty - issued_qty

3. PARTIAL FULFILLMENT

If some lines issued partially:

Request state becomes:

partial

If all lines fully issued:

Request state becomes:

done

4. SIGNATURE CAPTURE

Before confirm issue, require signatures:

Header fields:
issuer_signature = fields.Binary()
receiver_signature = fields.Binary()

issued_by = fields.Many2one(res.users)
received_by = fields.Many2one(hr.employee)

issued_datetime = fields.Datetime()

Use Odoo signature widget.

Need two signature blocks:

Warehouse issuer
Employee receiver

Both required before validation.

5. CREATE REAL STOCK PICKING

Do NOT create transfer using requested qty anymore.

Create stock.picking based on actual issued qty only.

Only lines with:

issued_qty > 0

Generate stock.move with:

product_uom_qty = issued_qty
quantity_done = issued_qty

Use source location from request.

Use destination location = consumption location.

6. STATE MACHINE UPGRADE

Current states:

draft
to_approve
approved
done
rejected

Upgrade to:

draft
to_approve
approved
issuing
partial
done
rejected

Logic:

Approved → Start Issue → issuing

After confirm:

If all fulfilled = done

If some remaining = partial

7. PDF REPORT

Create report:

Internal Consume Slip

Must show:

Request No
Employee
Department
Date
Requested Qty
Issued Qty
Remaining Qty
Issuer Signature
Receiver Signature
8. CHATTER / AUDIT LOG

Track:

issue started
qty changed
signatures completed
transfer created
partial completed

Use message_post.

9. SECURITY

Only group:

stock.group_stock_user

Can process issue.

Only manager can approve.

Employee can view own requests.

10. UI REQUIREMENTS
Request Form

Add smart buttons:

Transfers
Issue Slip

Add tab:

Issue Details

Show:

issued by
signatures
issue datetime
11. TECHNICAL REQUIREMENTS

Use Odoo 17 standards.

Must use:

models
views
security ir.model.access.csv
barcode JS / OWL if needed
qweb report
chatter mixin if suitable

No hacks.

No direct SQL unless necessary.

Use ORM.

12. CODE QUALITY

Write production-grade clean code.

Use methods:

action_start_issue()
action_confirm_issue()
_create_actual_picking()
_compute_remaining_qty()
_check_signature_required()
13. DELIVERABLES

Generate complete module patch including:

manifest.py changes
python model inheritance
XML views
security
report XML
barcode mobile assets
JS OWL components if needed
14. IMPORTANT BUSINESS RULES

If issued_qty = 0 for all lines:

Block confirm.

If no signatures:

Block confirm.

If stock insufficient during issue:

Show warning and allow lower qty issue.

Never create negative stock automatically.

15. OUTPUT FORMAT

Provide complete file-by-file implementation:

models/internal_consume_request.py
models/internal_consume_request_line.py
views/request_views.xml
views/barcode_templates.xml
static/src/js/barcode_issue.js
report/consume_slip.xml
security/ir.model.access.csv

Include full code.

No explanations only.

Build ready to install.