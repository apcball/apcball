# Marketplace Settlement - New Workflow Implementation

## Overview

The marketplace settlement module has been enhanced to implement the new workflow that separates fee handling from settlement creation. This ensures proper VAT recovery and withholding tax documentation while simplifying the settlement process.

## New Workflow Principle

**Key Concept**: Fees and taxes should be handled through proper vendor bills for accurate tax documentation, NOT through settlement deductions.

### Benefits of New Workflow:
1. **Proper VAT Recovery**: VAT on fees is recorded as input tax through vendor bills
2. **Correct WHT Documentation**: Withholding tax certificates are properly linked to vendor bills
3. **Simplified Settlement**: Settlement wizard only groups customer invoices
4. **Accurate GL**: No duplicate expense entries
5. **Better Reconciliation**: Clear AR/AP netting process

## Implementation Details

### 1. Removed from Settlement Wizard:
- ✅ Deduction fields (fee_amount, vat_on_fee_amount, wht_amount)
- ✅ Account selection for fees (fee_account_id, vat_account_id, wht_account_id)
- ✅ Validation logic for fee accounts
- ✅ Fee-related computations in settlement amounts

### 2. Enhanced Settlement Model:
- ✅ Removed deduction fields from settlement model
- ✅ Updated amount calculations to exclude deductions
- ✅ Simplified settlement move creation (no deduction entries)
- ✅ Enhanced AR/AP netting functionality

### 3. Enhanced AR/AP Netting:
- ✅ Improved vendor bill linking mechanism
- ✅ Preview wizard for netting calculations
- ✅ Better reconciliation logic
- ✅ Clear workflow guidance

### 4. New Action Methods:
- ✅ `action_link_vendor_bills()` - Link vendor bills to settlement
- ✅ `action_preview_netting()` - Preview AR/AP netting
- ✅ `action_create_vendor_bill_shopee()` - Quick Shopee bill creation
- ✅ `action_create_vendor_bill_spx()` - Quick SPX bill creation
- ✅ `get_workflow_status()` - Check workflow completion
- ✅ `get_workflow_guidance()` - Get next steps

## New Workflow Steps

### 1. Create Customer Invoices
```
Standard customer invoices → Posted
```

### 2. Create Settlement
```
Marketplace Settlement Wizard:
- Select trade channel (Shopee/SPX/etc.)
- Select customer invoices
- Create settlement → AR-Shopee created
```

### 3. Create Vendor Bills Separately
```
Shopee Vendor Bill (TR document):
- Commission fees
- Payment fees  
- VAT on fees (input tax)
- WHT (if applicable)

SPX Vendor Bill (RC document):
- Delivery fees
- WHT 1% (if applicable)
```

### 4. Link Vendor Bills to Settlement
```
Use "Link Vendor Bills" action:
- Select relevant vendor bills
- Link to settlement
```

### 5. Perform AR/AP Netting
```
Use "Net-off AR/AP" button:
- Preview netting amounts
- Confirm netting
- System creates offsetting entries
```

### 6. Bank Reconciliation
```
Reconcile remaining net amount with bank statement:
- If net positive: Money received from marketplace
- If net negative: Money paid to marketplace  
- If zero: Perfect netting (no bank transaction)
```

## Example Journal Entries

### Before (Old Workflow - with issues):
```
Settlement Entry:
Dr. AR-Customer-A          1,000
Dr. AR-Customer-B          2,000  
Dr. Commission Expense       150  ← Duplicate entry
Dr. VAT Input Tax             15  ← No proper tax document
Dr. WHT Payable              50   ← No WHT certificate
    Cr. AR-Shopee                 2,865
```

### After (New Workflow - correct):

**Step 1: Settlement Entry**
```
Dr. AR-Customer-A          1,000
Dr. AR-Customer-B          2,000
    Cr. AR-Shopee                 3,000  ← Full amount
```

**Step 2: Shopee Vendor Bill**
```
Dr. Commission Expense       150  ← Proper expense with tax document
Dr. VAT Input Tax             15  ← Proper VAT recovery
    Cr. AP-Shopee                  150
    Cr. WHT Payable                 15  ← Proper WHT with certificate
```

**Step 3: AR/AP Netting**
```
Dr. AP-Shopee               150
    Cr. AR-Shopee                  150  ← Offset receivable vs payable
```

**Result: Net AR-Shopee = 2,850** (to reconcile with bank)

## Technical Implementation

### Settlement Wizard Changes:
```python
# Removed deduction fields
# fee_amount = fields.Monetary(...)  # REMOVED
# vat_on_fee_amount = fields.Monetary(...)  # REMOVED  
# wht_amount = fields.Monetary(...)  # REMOVED

# Updated computation
@api.depends('invoice_ids')  # Removed deduction dependencies
def _compute_total_amount(self):
    for record in self:
        record.total_amount = sum(record.invoice_ids.mapped('amount_residual'))
        record.total_deductions = 0.0  # No deductions in settlement
        record.net_settlement_amount = record.total_amount
```

### Settlement Model Changes:
```python
# Removed deduction fields from model
# fee_amount = fields.Monetary(...)  # REMOVED
# Updated amount calculations
@api.depends('invoice_ids', 'vendor_bill_ids')  # Removed fee dependencies
def _compute_amounts(self):
    # Simplified calculation without deductions
    record.net_settlement_amount = total_invoice  # No deductions
```

### Enhanced AR/AP Netting:
```python
def action_preview_netting(self):
    """Preview AR/AP netting before execution"""
    preview_data = self._calculate_netting_preview()
    return wizard_action

def _calculate_netting_preview(self):
    """Calculate netting amounts and provide details"""
    # Calculate receivables vs payables
    # Provide detailed breakdown
```

## View Updates Required

The following views need to be updated to reflect the new workflow:

### 1. Settlement Wizard View:
- Remove deduction amount fields
- Remove account selection fields  
- Add workflow guidance
- Add quick action buttons for vendor bills

### 2. Settlement Form View:
- Remove deduction fields display
- Add vendor bill section
- Add netting action buttons
- Add workflow status indicator

### 3. Settlement Tree View:
- Update computed fields display
- Remove deduction columns

## User Training Points

1. **Separate Processes**: Settlement ≠ Fee Recording
2. **Proper Documentation**: Always use vendor bills for fees
3. **VAT Recovery**: Input tax only through vendor bills
4. **WHT Certificates**: Must be linked to vendor bills
5. **Netting Process**: Use preview before confirming
6. **Bank Reconciliation**: Only net amount needs reconciling

## Migration Considerations

For existing settlements with deduction data:
1. Keep old fields as computed/readonly for reference
2. Add migration script to convert old deductions to vendor bills
3. Provide clear upgrade documentation
4. Maintain backward compatibility where possible

## Testing Scenarios

1. **Complete Workflow**: Invoice → Settlement → Vendor Bills → Netting → Bank
2. **Multiple Bills**: Settlement with multiple linked vendor bills
3. **Perfect Netting**: Zero net amount after netting
4. **Partial Netting**: Some bills not linked
5. **Error Handling**: Proper validation at each step

## Benefits Achieved

✅ **Proper VAT Documentation**: Input tax properly recorded  
✅ **WHT Certificates**: Linked to correct vendor bills  
✅ **No Duplicate Entries**: Fees recorded once in vendor bills  
✅ **Clear Audit Trail**: Separate documents for different purposes  
✅ **Simplified Reconciliation**: Only net amount needs bank reconciliation  
✅ **Better Reporting**: Clear separation of settlement vs. fees  
✅ **Compliance**: Proper tax documentation for audits

This implementation follows Thai accounting standards and best practices for marketplace settlements while providing a clean, auditable workflow.
