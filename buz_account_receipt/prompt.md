Feature: Line-level Payment Registration + Payment Summary Smart Button
Context

The existing account.receipt.voucher aggregates multiple account.receipt records (one per customer).
Now we want to add line-level payment registration and a smart button summarizing all generated payments linked to the voucher.

1. Line-level Payment Registration
Model: account.receipt.voucher.line

Add a button “Register Payment” (action_register_payment_line) on each line in the form view.

When clicked:

Retrieve the related account.receipt record (field: receipt_id).

Extract all invoices from that receipt (receipt.line_ids.mapped('move_id')) that are posted and still have residual amounts (amount_residual_signed != 0).

Call Odoo’s standard payment wizard (account.payment.register) with:

ctx = {
    'active_model': 'account.move',
    'active_ids': move_ids,
    'default_communication': f"Receipt {receipt.name}",
    'default_payment_date': parent_voucher.date,
    'default_journal_id': config_journal_id,  # optional default
    'default_payment_type': 'inbound',
}


Return action from account.action_account_payment_from_invoices with updated context.

After the payment is created and posted, link it back to the voucher via a relational field.

Add relational field on line:
payment_ids = fields.Many2many(
    'account.payment',
    'account_receipt_voucher_line_payment_rel',
    'voucher_line_id', 'payment_id',
    string='Related Payments',
    readonly=True,
)

Optional:

If multiple payments were made for the same line, all of them should be listed here.

2. Smart Button: Payment Summary on Voucher
Model: account.receipt.voucher

Add a computed field:

payment_count = fields.Integer(
    compute="_compute_payment_count",
    string="Payments"
)


Compute:

@api.depends('line_ids.payment_ids')
def _compute_payment_count(self):
    for rec in self:
        rec.payment_count = len(rec.mapped('line_ids.payment_ids'))


Add smart button in form view header:

Label: “Payments”

Icon: “fa-money” or “fa-credit-card”

Counter: payment_count

Action:

def action_open_related_payments(self):
    payments = self.mapped('line_ids.payment_ids')
    return {
        'name': 'Payments',
        'type': 'ir.actions.act_window',
        'res_model': 'account.payment',
        'view_mode': 'tree,form',
        'domain': [('id', 'in', payments.ids)],
    }

3. Behavior Summary
Action	Effect
Click “Register Payment” on RV line	Opens standard payment wizard pre-filled for invoices in that Receipt
Complete payment	Creates standard account.payment record and reconciles invoices
After posting	Payment automatically linked to that RV line (via payment_ids)
Smart Button “Payments”	Opens list of all payments created from lines under this RV
Payment count	Updates automatically when new payments are linked
4. Optional Enhancements

Add field payment_state on each line (computed from linked account.payment):

payment_state = fields.Selection([
    ('not_paid','Not Paid'),
    ('in_payment','In Payment'),
    ('paid','Paid')
], compute="_compute_payment_state", store=True)


On compute, check if all linked payments are posted/reconciled → mark “Paid”.

In the RV tree view, add column Payment Count or icon indicator per line.

5. Example User Flow (AR)

User creates RV containing 3 receipts (customers A, B, C).

Each line shows: Receipt, Partner, Amount, and a “Register Payment” button.

Accountant clicks “Register Payment” on line 1 → opens wizard for that customer’s invoices → posts payment.

Payment is created and automatically linked to that line.

Smart button on RV shows “Payments (3)” after all 3 lines are paid.

Clicking the smart button opens all payment records related to the RV.

6. Optional: Apply Same Design to AP (Payment Voucher)

In account.payment.voucher.line, implement same logic:

Button “Register Payment” → create outbound payment (payment_type='outbound', partner_type='supplier').

Link payments via payment_ids.

Smart button on PV form → open all related payments.

7. Acceptance Criteria

✅ Each RV line can individually trigger its own payment registration
✅ Payment wizard opens with correct invoices for that receipt’s customer
✅ Once payment is posted, linked to RV line and visible under smart button
✅ RV smart button shows correct count and list of related payments
✅ Works with multi-customer RVs (each line independent)
✅ Optional: same logic applied for AP Payment Voucher (outbound)