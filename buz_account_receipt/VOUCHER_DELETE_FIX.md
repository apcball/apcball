# Voucher Delete Fix - FK Constraint Resolution

## Problem Statement

**Error:** Validation Error when deleting receipt vouchers or voucher lines:
```
The operation cannot be completed: another model requires the record being deleted. 
If possible, archive it instead.

Model: Unknown (unknown)
Constraint: account_receipt_voucher_line_payment_rel_voucher_line_id_fkey
```

**Root Cause:**
- The `account.receipt.voucher.line` model has a Many2many relationship with `account.payment` via the relation table `account_receipt_voucher_line_payment_rel`
- When attempting to delete a voucher or voucher line, PostgreSQL enforces the foreign key constraint
- The relation table still contains references to the voucher line being deleted
- PostgreSQL refuses to delete the voucher line because of the FK constraint

## Solution Implemented

Added `unlink()` method overrides to both models to clear Many2many relations before deletion:

### 1. AccountReceiptVoucherLine.unlink()
**Location:** `models/account_receipt_voucher.py` (line ~685)

```python
def unlink(self):
    """Ensure Many2many links to payments are removed before deleting voucher lines.

    Postgres will prevent deleting a record that is referenced by a foreign key
    from the M2M relation table. We explicitly clear the relation rows so the
    voucher line can be removed (this mirrors an "archive instead" behaviour
    when needed).
    """
    # Clear m2m links to avoid FK restriction errors on delete
    for line in self:
        if line.payment_ids:
            # Remove all links in the relation table for this line
            line.write({'payment_ids': [(5, 0, 0)]})
    return super(AccountReceiptVoucherLine, self).unlink()
```

**What it does:**
- Iterates through each voucher line being deleted
- Checks if the line has any linked payments (`payment_ids`)
- Clears the Many2many relation using command `(5, 0, 0)` which removes all links
- Then proceeds with the normal deletion via `super().unlink()`

### 2. AccountReceiptVoucher.unlink()
**Location:** `models/account_receipt_voucher.py` (line ~408)

```python
def unlink(self):
    """Clear related payment M2M links on voucher lines before deleting the voucher.

    Deleting a voucher may cascade-delete its voucher lines at the database level,
    which can cause a FK constraint if the M2M relation table still references
    those lines. We proactively clear the M2M rows.
    """
    for voucher in self:
        # Clear links on each line to avoid DB FK errors during cascade delete
        for line in voucher.line_ids:
            if line.payment_ids:
                line.write({'payment_ids': [(5, 0, 0)]})
    return super(AccountReceiptVoucher, self).unlink()
```

**What it does:**
- Iterates through each voucher being deleted
- For each voucher, iterates through all its lines (`line_ids`)
- Clears payment links on each line before the voucher deletion cascades
- Then proceeds with the normal deletion via `super().unlink()`

## Technical Details

### Many2many Relation Structure
```python
payment_ids = fields.Many2many(
    'account.payment',
    'account_receipt_voucher_line_payment_rel',  # Relation table name
    'voucher_line_id',  # Column for voucher line FK
    'payment_id',       # Column for payment FK
    string='Related Payments',
    readonly=True,
)
```

### Odoo M2M Command (5, 0, 0)
- Command `5` = Remove all records from the relation
- First `0` = No specific ID (not used for command 5)
- Second `0` = No specific ID (not used for command 5)
- Effect: Deletes all rows from `account_receipt_voucher_line_payment_rel` where `voucher_line_id` matches the current line

### Alternative M2M Commands (for reference)
- `(3, id)` - Remove a specific link by ID
- `(6, 0, [ids])` - Replace all links with a new set
- `(4, id)` - Add a link to an existing record

## Why This Approach

### Advantages:
1. **Clean deletion:** Properly removes database references before deletion
2. **No data loss:** Only removes the M2M relation, not the payment records themselves
3. **Database integrity:** Respects PostgreSQL FK constraints
4. **Automatic:** Users don't need to manually unlink payments first

### Alternative Approaches (not implemented):
1. **Refuse deletion:** Raise UserError if payments are linked (too restrictive)
2. **Archive instead:** Prevent deletion entirely (changes user workflow)
3. **Cascade delete payments:** Would lose payment data (dangerous)

## Testing Recommendations

### Test Case 1: Delete Voucher Line with Linked Payments
```python
# 1. Create a voucher with lines
voucher = env['account.receipt.voucher'].create({...})
line = env['account.receipt.voucher.line'].create({
    'voucher_id': voucher.id,
    'receipt_id': receipt.id,
})

# 2. Confirm voucher (creates payments and links them)
voucher.action_confirm()

# 3. Attempt to delete the line
line.unlink()  # Should succeed without FK error
```

### Test Case 2: Delete Entire Voucher
```python
# 1. Create and confirm voucher (with payments)
voucher = env['account.receipt.voucher'].create({...})
voucher.action_confirm()

# 2. Attempt to delete the entire voucher
voucher.unlink()  # Should succeed without FK error
```

### Test Case 3: Delete Draft Voucher (No Payments)
```python
# 1. Create voucher in draft state
voucher = env['account.receipt.voucher'].create({...})

# 2. Delete without confirming
voucher.unlink()  # Should succeed (no payments to clear)
```

## Deployment Status

- **Date Fixed:** 2025-10-07
- **Files Modified:** 
  - `/opt/instance1/odoo17/custom-addons/buz_account_receipt/models/account_receipt_voucher.py`
- **Instance Restarted:** Yes (2025-10-07 15:00:44 UTC)
- **Status:** ✅ Active and running
- **Methods Added:**
  - `AccountReceiptVoucher.unlink()` at line 402
  - `AccountReceiptVoucherLine.unlink()` at line 700

## Verification Steps

1. **Check service status:**
   ```bash
   sudo systemctl status instance1
   ```

2. **Test in Odoo UI:**
   - Navigate to Accounting > Receipt Vouchers
   - Create a new voucher with multiple lines
   - Confirm the voucher (creates payments)
   - Try to delete a voucher line → Should succeed
   - Try to delete the entire voucher → Should succeed

3. **Check database (optional):**
   ```sql
   -- Check if relation table is cleaned up after delete
   SELECT * FROM account_receipt_voucher_line_payment_rel 
   WHERE voucher_line_id NOT IN (
       SELECT id FROM account_receipt_voucher_line
   );
   -- Should return 0 rows (no orphaned relations)
   ```

## Related Models

- `account.receipt.voucher` - Main voucher model
- `account.receipt.voucher.line` - Voucher line model (has the M2M field)
- `account.payment` - Payment model (referenced by M2M)
- `account_receipt_voucher_line_payment_rel` - Database relation table

## Notes

- The fix does NOT delete payment records, only the M2M links
- Payment records remain in the database and can be viewed/managed independently
- If you need to preserve the relationship for audit purposes, consider implementing an archive mechanism instead
- The `ondelete="cascade"` on `voucher_id` field ensures lines are deleted when voucher is deleted

## Future Enhancements (Optional)

1. **Audit trail:** Log a message in chatter when M2M links are cleared during deletion
2. **Confirmation dialog:** Show a warning to users before deleting vouchers with payments
3. **Soft delete:** Implement archival instead of hard deletion for better audit trails
4. **Unlink validation:** Add business logic to prevent deletion in certain states

## Conclusion

The FK constraint error is now resolved. Users can delete vouchers and voucher lines without encountering the database constraint violation. The fix is minimal, surgical, and maintains data integrity by properly cleaning up Many2many relations before deletion.
