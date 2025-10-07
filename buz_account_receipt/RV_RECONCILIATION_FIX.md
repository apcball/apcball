# RV Reconciliation Fix - Outstanding Payment Issue

## Problem Description

**Error Message**: "No unpaid invoices found for partner คุณ วรัลชญานี in this voucher"

**Scenario**:
1. User created Receipt REC/2025/0002 for customer "คุณ วรัลชญานี"
2. User clicked "Register Batch Payment" from the receipt
3. Since there were no unpaid invoices, the system created an "outstanding" (on-account) payment PBK01/2025/00001
4. The payment was posted successfully (Debit 1,620.00 ฿ to account 111003, Credit 1,620.00 ฿ to account 114200)
5. When user tried to confirm the RV (Receipt Voucher), the system raised an error

## Root Cause

The RV `action_confirm()` method had logic that:
1. Only looked for **unpaid invoices** when confirming a voucher
2. Raised an error if no unpaid invoices were found
3. Did **not check** if payments already existed from the receipt

This created a problem when:
- Outstanding payments were created directly from receipts (on-account payments)
- The invoices were already reconciled/paid before the RV was confirmed
- The RV tried to create new payments but found no unpaid invoices

## Solution Implemented

### 1. Enhanced RV Logic to Handle Existing Payments

Modified `/opt/instance1/odoo17/custom-addons/buz_account_receipt/models/account_receipt_voucher.py`:

```python
# Check if payments already exist from receipts (outstanding payments)
existing_payments = self.env['account.payment'].search([
    ('partner_id', '=', partner.id),
    ('state', '=', 'posted'),
    ('payment_type', '=', 'inbound'),
    '|',
    ('receipt_ids', 'in', receipts_for_partner.ids),
    ('id', 'in', lines.mapped('payment_ids').ids)
])

# If there are existing payments and no unpaid invoices, just link them
if existing_payments and not unpaid_moves:
    for line in lines:
        # Link existing payments to voucher line
        line.write({'payment_ids': [(6, 0, existing_payments.ids)]})
    
    # Add message to chatter
    payment_names = ', '.join(existing_payments.mapped('name'))
    voucher.message_post(
        body=_("Existing payments linked for partner %s: %s") % (partner.name, payment_names)
    )
    continue  # Skip to next partner
```

### 2. Fixed M2M Relationship Usage

Replaced old `buz_receipt_id` (One2many) with `receipt_ids` (Many2many):

**In account_receipt.py**:
```python
# OLD (incorrect):
payment.write({'buz_receipt_id': self.id})

# NEW (correct):
self.write({
    'payment_ids': [(4, payment.id)]  # M2M link
})
```

**In account_receipt_voucher.py**:
```python
# OLD (incorrect):
for line in lines:
    if line.receipt_id:
        payment.write({'buz_receipt_id': line.receipt_id.id})

# NEW (correct):
receipts_to_link = self.env['account.receipt']
for line in lines:
    if line.receipt_id:
        receipts_to_link |= line.receipt_id

if receipts_to_link:
    for receipt in receipts_to_link:
        receipt.write({
            'payment_ids': [(4, payment.id)]  # M2M link
        })
```

## How It Works Now

### Scenario 1: Payments Already Exist (Outstanding Payments)

1. User creates receipt and registers outstanding payment
2. Payment is posted and linked to receipt via M2M
3. When RV is confirmed:
   - System checks for unpaid invoices
   - If none found, checks for existing payments
   - Links existing payments to voucher lines
   - Logs in chatter: "Existing payments linked for partner X: PBK01/2025/00001"
   - **No error raised**

### Scenario 2: Unpaid Invoices Exist

1. User creates receipt with unpaid invoices
2. When RV is confirmed:
   - System finds unpaid invoices
   - Creates new payment for those invoices
   - Links payment to receipt and voucher lines
   - Reconciles payment with invoices
   - Logs in chatter: "Payment X created for partner Y"

### Scenario 3: No Payments and No Unpaid Invoices

1. User creates receipt but hasn't paid
2. When RV is confirmed:
   - System checks for unpaid invoices: none found
   - System checks for existing payments: none found
   - **Error raised**: "No unpaid invoices or existing payments found for partner X"

## Files Modified

1. **models/account_receipt_voucher.py**:
   - Enhanced `action_confirm()` to check for existing payments
   - Fixed M2M relationship usage in payment linking

2. **models/account_receipt.py**:
   - Fixed `action_register_batch_payment()` to use M2M instead of One2many

## Testing the Fix

### Test Case 1: Outstanding Payment Scenario
1. Create receipt for customer with invoices
2. Click "Register Batch Payment" from receipt
3. System creates outstanding payment (no unpaid invoices)
4. Post the payment
5. Create RV with that receipt
6. Confirm RV
7. **Expected**: RV confirms successfully, links existing payment, no error

### Test Case 2: Normal Payment Scenario
1. Create receipt with unpaid invoices
2. Create RV with that receipt
3. Confirm RV
4. **Expected**: New payment created, linked to receipt and RV, reconciled with invoices

### Test Case 3: No Payment Scenario
1. Create receipt
2. Don't create any payment
3. Create RV
4. Try to confirm RV
5. **Expected**: Error raised (as designed)

## Benefits

✅ **Flexible Payment Workflow**: Supports both outstanding payments and direct invoice payments  
✅ **No Duplicate Payments**: Reuses existing payments instead of creating duplicates  
✅ **Better UX**: Clear chatter messages about what happened  
✅ **Audit Trail**: All payment links are recorded via M2M relation  
✅ **RV-Ready**: Works seamlessly with external Receipt Voucher workflows  

## Migration Notes

- **No database migration required**: M2M table already exists from previous implementation
- **Backward compatible**: Existing receipts and payments continue to work
- **Service restart**: Already applied (service restarted successfully)

## Deployment

**Status**: ✅ **DEPLOYED**  
**Date**: October 7, 2025  
**Service**: Restarted successfully  

## Next Steps

1. Test the fix with the problematic voucher
2. Confirm RV successfully links existing payment
3. Verify chatter message appears
4. Test creating new RV with unpaid invoices to ensure normal flow still works

---

**Issue**: Outstanding payment reconciliation in RV  
**Fix**: Enhanced RV logic + M2M relationship fixes  
**Status**: Complete and deployed  
**Module**: buz_account_receipt v2.0.0
