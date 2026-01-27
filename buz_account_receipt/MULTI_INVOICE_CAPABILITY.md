# Multiple Invoice Support in Receipts Module

## Overview
The **buz_account_receipt** module fully supports adding multiple invoices to a single receipt.

## How It Works

### 1. **Receipt Line Structure**
- Each receipt has a `line_ids` field (One2many relationship)
- Each line represents ONE invoice
- You can add as many lines (invoices) as needed

### 2. **Adding Multiple Invoices**

#### Method A: From Invoice List View
1. Go to **Accounting > Customers > Invoices**
2. Select multiple invoices from the same customer
3. Click **Action > Create Receipt**
4. All selected invoices will be added to a single receipt

#### Method B: Manually in Receipt Form
1. Create a new receipt or open a draft receipt
2. Go to the **Invoice Lines** tab
3. Click "Add a line"
4. Select an invoice from the dropdown
5. Repeat steps 3-4 for each additional invoice

### 3. **Validation & Constraints**

The module enforces the following rules:

✅ **Allowed:**
- Multiple invoices per receipt
- Mix of invoices and credit notes
- Partial collection amounts

❌ **Not Allowed:**
- Same invoice added twice to one receipt
- Invoices from different customers
- Invoices from different companies
- Invoices already used in another receipt
- Different currencies (if setting enabled)

### 4. **Features**

#### Smart Filtering
The invoice dropdown automatically filters to show only:
- Posted invoices/credit notes
- Same partner as receipt
- Not already in this receipt
- Not already in another receipt

#### Duplicate Prevention
A constraint `_check_duplicate_invoice_in_receipt()` prevents adding the same invoice twice.

#### Amount Calculation
- `amount_total`: Sum of all "To Collect" amounts from lines
- `amount_invoice_total`: Sum of all invoice totals
- Each line shows: Invoice Total, Residual, Paid to Date, and To Collect

### 5. **Code References**

**Model Definition:**
```python
class AccountReceipt(models.Model):
    _name = "account.receipt"
    
    line_ids = fields.One2many("account.receipt.line", "receipt_id", string="Lines")
```

**Line Model:**
```python
class AccountReceiptLine(models.Model):
    _name = "account.receipt.line"
    
    receipt_id = fields.Many2one("account.receipt", required=True, ondelete="cascade")
    move_id = fields.Many2one("account.move", string="Invoice")
```

**Duplicate Check:**
```python
@api.constrains('move_id', 'receipt_id')
def _check_duplicate_invoice_in_receipt(self):
    """Prevent adding the same invoice multiple times to the same receipt"""
```

**View Configuration:**
```xml
<field name="line_ids">
    <tree editable="bottom">
        <field name="move_id" 
               domain="[('move_type', 'in', ['out_invoice', 'out_refund']), 
                        ('state', '=', 'posted'), 
                        ('partner_id', '=', parent.partner_id), 
                        ('id', 'not in', parent.used_move_ids)]"/>
        <!-- Other fields -->
    </tree>
</field>
```

## Example Workflow

### Scenario: Create a receipt for 3 invoices

1. **Customer**: ABC Company
2. **Invoices**:
   - INV/2024/0001: THB 10,000
   - INV/2024/0002: THB 15,000
   - INV/2024/0003: THB 8,500

**Steps:**
1. Go to Invoice list
2. Select all 3 invoices
3. Action > Create Receipt
4. Result: One receipt with 3 lines totaling THB 33,500

## Summary

✅ **YES** - The module fully supports multiple invoices per receipt
✅ **YES** - Both automatic (from invoice selection) and manual (form entry) methods
✅ **YES** - Complete validation and duplicate prevention
✅ **YES** - Production-ready and well-documented

The functionality is **already implemented** and working correctly!
