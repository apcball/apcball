# BUZ Account Receipt - Developer Quick Reference

## RV-Ready API Reference

### Method 1: Get Unpaid Invoices
```python
unpaid_moves = receipt.receipt_get_unpaid_moves()
# Returns: account.move recordset with residual > 0
```

### Method 2: Build Payment Context
```python
context = receipt.receipt_build_payment_context(
    journal_id=None,      # Optional: default journal
    memo_suffix=None      # Optional: append to communication
)
# Returns: dict with wizard context
```

### Method 3: Link Payments
```python
receipt.receipt_link_payments(payments)
# Parameters: payments = account.payment recordset
# Side effects: Updates M2M, logs in chatter, recomputes fields
```

### Method 4: Reconcile Payment (Optional)
```python
receipt.receipt_reconcile_with_payment(payment)
# Parameters: payment = account.payment record
# Side effects: Reconciles payment with invoice receivables
```

---

## Key Fields Reference

### account.receipt

| Field | Type | Computed | Description |
|-------|------|----------|-------------|
| `name` | Char | No | Receipt number (REC/YYYY/seq) |
| `date` | Date | No | Receipt date |
| `partner_id` | Many2one | No | Customer |
| `company_id` | Many2one | No | Company |
| `currency_id` | Many2one | Yes | From company |
| `state` | Selection | No | draft/posted/cancel |
| `amount_total` | Monetary | Yes | Sum of `line_ids.amount_to_collect` |
| `amount_invoice_total` | Monetary | Yes | Sum of invoice totals |
| `payment_ids` | Many2many | No | Linked payments |
| `payment_count` | Integer | Yes | Count of payments |
| `line_ids` | One2many | No | Receipt lines |

### account.receipt.line

| Field | Type | Computed | Description |
|-------|------|----------|-------------|
| `move_id` | Many2one | No | Invoice |
| `amount_total_signed` | Monetary | Yes | Invoice total (signed) |
| `amount_residual_signed` | Monetary | Yes | Invoice residual (signed) |
| `amount_paid_to_date` | Monetary | Yes | total_signed - residual_signed |
| `amount_to_collect` | Monetary | No | To collect this receipt (user-editable) |
| `currency_id` | Many2one | Yes | From receipt |

---

## Configuration Parameters

Access via: `env['ir.config_parameter'].sudo().get_param(key, default)`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `buz_account_receipt.auto_post_receipts` | bool | True | Auto-post on create |
| `buz_account_receipt.enforce_single_currency_per_receipt` | bool | True | Single currency constraint |
| `buz_account_receipt.default_bank_journal_id` | int | None | Default journal ID |
| `buz_account_receipt.allow_outstanding_fallback` | bool | True | Allow on-account payments |

---

## Common Usage Patterns

### Create Receipt from Invoices
```python
# From invoice list view (multi-select)
invoices = env['account.move'].browse(active_ids)
action = invoices.action_create_receipt_from_invoices()
# Returns action dict to open new receipt
```

### Register Batch Payment
```python
# From receipt form
receipt = env['account.receipt'].browse(receipt_id)
action = receipt.action_register_batch_payment()
# Opens payment wizard or creates outstanding payment
```

### Link External Payment to Receipt
```python
# From external RV module
payment = env['account.payment'].create({...})
receipt.receipt_link_payments(payment)
# Payment now linked via M2M
```

### Build Custom Payment Workflow
```python
# Get unpaid invoices
moves = receipt.receipt_get_unpaid_moves()

# Build context for wizard
context = receipt.receipt_build_payment_context(
    journal_id=bank_journal.id,
    memo_suffix="- Partial Payment"
)

# Open wizard with custom context
return {
    'type': 'ir.actions.act_window',
    'res_model': 'account.payment.register',
    'view_mode': 'form',
    'target': 'new',
    'context': context,
}
```

---

## Common Queries

### Get All Receipts for Customer
```python
receipts = env['account.receipt'].search([
    ('partner_id', '=', partner.id),
    ('state', '=', 'posted'),
])
```

### Get Receipts with Payments
```python
receipts = env['account.receipt'].search([
    ('payment_count', '>', 0),
])
```

### Get Payments for Receipt
```python
payments = receipt.payment_ids
# Or via SQL join
payments = env['account.payment'].search([
    ('receipt_ids', 'in', [receipt.id]),
])
```

### Get Receipts for Invoice
```python
receipt_lines = env['account.receipt.line'].search([
    ('move_id', '=', invoice.id),
])
receipts = receipt_lines.mapped('receipt_id')
```

---

## Constraints & Validations

### Automatic Validations
1. ✅ Same partner across all lines
2. ✅ Same company across all lines
3. ✅ Single currency (if enabled)
4. ✅ `amount_to_collect <= residual` (with 0.01 tolerance)
5. ✅ Posted invoices only
6. ✅ Customer invoices/refunds only

### Manual Validations in Your Code
```python
# Check if receipt can be posted
if not receipt.line_ids:
    raise UserError("No lines to post")

# Check if batch payment available
unpaid = receipt.receipt_get_unpaid_moves()
if not unpaid and not allow_outstanding:
    raise UserError("No unpaid invoices")

# Validate currency match
if receipt.currency_id != payment.currency_id:
    raise UserError("Currency mismatch")
```

---

## Security Groups

### Access Control
```python
# Check if user can create receipts
if env.user.has_group('account.group_account_invoice'):
    # Can create/read/write receipts
    pass

if env.user.has_group('account.group_account_manager'):
    # Can also delete receipts
    pass
```

### Programmatic Access
```python
# Bypass access rights (use carefully!)
receipt = env['account.receipt'].sudo().browse(receipt_id)

# With specific company
receipt = env['account.receipt'].with_company(company).create({...})
```

---

## Report Customization

### Available Variables in QWeb
```xml
<t t-foreach="doc.line_ids" t-as="line">
    <span t-field="line.move_id.name"/>              <!-- Invoice number -->
    <span t-field="line.move_id.invoice_date"/>      <!-- Invoice date -->
    <span t-field="line.amount_total_signed"/>       <!-- Signed total -->
    <span t-field="line.amount_paid_to_date"/>       <!-- Paid to date -->
    <span t-field="line.amount_to_collect"/>         <!-- To collect -->
    <t t-set="residual_after" t-value="line.amount_residual_signed - line.amount_to_collect"/>
    <span t-esc="'{:,.2f}'.format(residual_after)"/> <!-- Residual after -->
</t>

<!-- Totals -->
<span t-field="doc.amount_total"/>                   <!-- This payment -->
<span t-field="doc.amount_invoice_total"/>           <!-- Invoice total -->
<span t-esc="doc.amount_total_words"/>               <!-- Amount in words -->
```

---

## Testing Helpers

### Create Test Data
```python
# Create partner
partner = env['res.partner'].create({
    'name': 'Test Customer',
    'customer_rank': 1,
})

# Create invoice
invoice = env['account.move'].create({
    'move_type': 'out_invoice',
    'partner_id': partner.id,
    'invoice_date': fields.Date.today(),
    'invoice_line_ids': [(0, 0, {
        'product_id': product.id,
        'quantity': 1,
        'price_unit': 100,
    })]
})
invoice.action_post()

# Create receipt
receipt = env['account.receipt'].create({
    'partner_id': partner.id,
    'line_ids': [(0, 0, {
        'move_id': invoice.id,
        'amount_to_collect': invoice.amount_residual,
    })]
})
```

### Run Tests
```bash
# Run all module tests
./odoo-bin -d test_db -i buz_account_receipt --test-enable --stop-after-init

# Run specific test
./odoo-bin -d test_db --test-enable --stop-after-init \
  --test-tags /buz_account_receipt:TestBuzAccountReceipt.test_create_receipt_from_invoices
```

---

## Troubleshooting

### Debug Mode
```python
import logging
_logger = logging.getLogger(__name__)

# Log receipt creation
_logger.info("Creating receipt for partner: %s", partner.name)
_logger.debug("Receipt lines: %s", receipt.line_ids)
```

### Check Computed Fields
```python
# Force recompute
receipt._compute_amount_total()
receipt._compute_payment_count()

# Check stored values
_logger.info("Amount total: %s", receipt.amount_total)
_logger.info("Payment count: %s", receipt.payment_count)
```

### Inspect M2M Relation
```python
# Check M2M table directly
env.cr.execute("""
    SELECT receipt_id, payment_id 
    FROM account_receipt_payment_rel 
    WHERE receipt_id = %s
""", [receipt.id])
links = env.cr.fetchall()
_logger.info("M2M links: %s", links)
```

---

## Best Practices

### ✅ DO:
- Use `receipt_link_payments()` for linking payments
- Use `receipt_get_unpaid_moves()` before opening payment wizard
- Check `payment_count > 0` before showing payment button
- Use signed amounts for refund calculations
- Validate currency/partner/company before creating lines
- Test with mixed invoices and refunds

### ❌ DON'T:
- Directly modify M2M table (use helper methods)
- Ignore `amount_to_collect` constraint
- Mix currencies without checking config
- Create receipts across companies
- Bypass validations with `sudo()` unless necessary
- Forget to call `action_post()` in auto-post scenarios

---

## Performance Tips

1. **Batch Operations**: Use `create()` with list of vals instead of loops
2. **Prefetch**: Use `mapped()` and `filtered()` for efficient recordset operations
3. **Computed Fields**: Already optimized with `store=True` where appropriate
4. **Indexes**: M2M relation has automatic indexes on both columns

---

## External Integration (RV Module)

Example RV module integration:
```python
# In your RV module
class AccountReceiptVoucher(models.Model):
    _name = 'account.receipt.voucher'
    
    receipt_ids = fields.Many2many('account.receipt')
    
    def action_register_payments(self):
        """Register payments for all receipts in this voucher"""
        for receipt in self.receipt_ids:
            # Get unpaid invoices
            moves = receipt.receipt_get_unpaid_moves()
            
            if moves:
                # Build context
                context = receipt.receipt_build_payment_context(
                    journal_id=self.journal_id.id,
                    memo_suffix=f"- Voucher {self.name}"
                )
                
                # Create payment
                payment = env['account.payment'].with_context(context).create({
                    'amount': sum(moves.mapped('amount_residual')),
                    # ... other fields
                })
                
                # Link to receipt
                receipt.receipt_link_payments(payment)
                
                # Optional: Auto-reconcile
                receipt.receipt_reconcile_with_payment(payment)
```

---

**Quick Reference Version**: 2.0.0  
**Last Updated**: October 7, 2025  
**Module**: buz_account_receipt  

For complete documentation, see `IMPLEMENTATION_SUMMARY.md`
